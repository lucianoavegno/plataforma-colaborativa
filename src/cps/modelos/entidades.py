"""Esquema relacional del instrumento.

El esquema está organizado alrededor de tres nociones que la versión anterior
del sistema confundía:

* **Instancia**: el problema con su partición. Es contenido, es versionado, y no
  cambia entre modalidades.
* **Episodio**: un intento de resolución bajo una modalidad y una condición
  experimental. Reemplaza a la antigua "sesión", que mezclaba el registro de
  actividad del usuario con la unidad de análisis.
* **Medición**: lo que se computa *sobre* instancias y episodios. Vive en tablas
  aparte porque una medición puede recalcularse, y recalcularla no debe pisar el
  dato observado.

Esa última separación es la que permite volver a codificar transcripts con otro
juez, o volver a estimar la competencia con otro solver, sin perder el historial
ni contaminar los datos crudos.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cps.modelos.base import Base, MarcaTemporal, ahora

# ---------------------------------------------------------------------------
# Vocabularios
# ---------------------------------------------------------------------------


class Rol(StrEnum):
    """Nivel de acceso de una cuenta.

    La distinción es de protección de datos, no de comodidad: un participante no
    debe poder leer los datos privados de las instancias que todavía no resolvió,
    ni los episodios de otras personas.
    """

    PARTICIPANTE = "participante"
    INVESTIGADOR = "investigador"


class Modalidad(StrEnum):
    AGENTE_AGENTE = "agente_agente"
    AGENTE_ESTUDIANTE = "agente_estudiante"
    RESOLUCION_DIRECTA = "resolucion_directa"
    """Consulta de la resolución completa. No es una modalidad de estudio: se
    registra para saber quién vio la solución, porque eso invalida sus episodios
    posteriores sobre la misma instancia."""


class CondicionDivulgacion(StrEnum):
    """Factor experimental cruzado con la modalidad.

    La restricción se trata como condición y no como corrección del instrumento:
    prohibir por prompt que se divulgue el dato en el primer turno sustituye el
    fenómeno que se quiere observar (la conducta comunicativa espontánea) por
    otro (la obediencia a la restricción).
    """

    LIBRE = "libre"
    RESTRINGIDA = "restringida"


class LadoAsignado(StrEnum):
    """Qué dato privado recibe el participante humano.

    Contrabalancear esto es obligatorio. En agente-agente ambos roles son
    artificiales, así que si en agente-estudiante el humano ocupara siempre el
    mismo lado, la comparación entre modalidades quedaría confundida con el
    efecto del rol.
    """

    A = "a"
    B = "b"


class EstadoEpisodio(StrEnum):
    EN_CURSO = "en_curso"
    FINALIZADO = "finalizado"
    ABANDONADO = "abandonado"
    """Cerrado sin respuesta final. Es dato faltante, no fracaso."""


class RolTurno(StrEnum):
    SISTEMA = "sistema"
    PARTICIPANTE_A = "participante_a"
    PARTICIPANTE_B = "participante_b"


class TipoAutor(StrEnum):
    """Si el turno lo produjo un modelo o una persona.

    Se guarda por separado del rol porque el mismo rol puede estar ocupado por
    un modelo o por un estudiante según la modalidad, y el análisis necesita
    distinguirlos sin reconstruirlo desde la modalidad del episodio.
    """

    MODELO = "modelo"
    HUMANO = "humano"
    SISTEMA = "sistema"


# ---------------------------------------------------------------------------
# Cuentas y consentimiento
# ---------------------------------------------------------------------------


class Cuenta(Base):
    """Una cuenta del sistema.

    El correo electrónico es dato identificatorio y se guarda separado del
    seudónimo. La exportación de datos usa el seudónimo y nunca el correo.
    """

    __tablename__ = "cuentas"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    hash_password: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default=Rol.PARTICIPANTE, index=True)

    seudonimo: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        doc="Identificador estable y no reversible usado en toda exportación.",
    )

    creada_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)

    consentimientos: Mapped[list[Consentimiento]] = relationship(
        back_populates="cuenta", cascade="all, delete-orphan"
    )
    episodios: Mapped[list[Episodio]] = relationship(
        back_populates="cuenta", cascade="all, delete-orphan"
    )

    @property
    def es_investigador(self) -> bool:
        return self.rol == Rol.INVESTIGADOR


class Consentimiento(Base):
    """Registro de consentimiento informado.

    Se guarda la versión del texto aceptado, no sólo la fecha: si el texto
    cambia, hay que saber qué aceptó cada persona. El retiro no borra la fila,
    la marca, porque hace falta poder demostrar que el retiro se respetó.
    """

    __tablename__ = "consentimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"), index=True)

    version_texto: Mapped[str] = mapped_column(String(32))
    hash_texto: Mapped[str] = mapped_column(String(64))
    otorgado_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)
    retirado_en: Mapped[datetime | None] = mapped_column(MarcaTemporal, nullable=True)

    cuenta: Mapped[Cuenta] = relationship(back_populates="consentimientos")

    @property
    def vigente(self) -> bool:
        return self.retirado_en is None


# ---------------------------------------------------------------------------
# Banco de instancias
# ---------------------------------------------------------------------------


class Instancia(Base):
    """Un problema con partición de información.

    El campo ``hash_contenido`` es lo que vuelve reproducible al banco: si una
    instancia se edita, su hash cambia y las mediciones viejas quedan
    identificables como referidas a otra versión del contenido. La versión
    anterior del sistema hacía *upsert* por título, de modo que una corrección
    silenciosa del enunciado invalidaba mediciones anteriores sin dejar rastro.
    """

    __tablename__ = "instancias"
    __table_args__ = (
        UniqueConstraint("codigo", "version", name="codigo_version"),
        CheckConstraint("dificultad_declarada BETWEEN 1 AND 5", name="dificultad_valida"),
        Index("ix_instancias_area_activa", "area", "activa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(
        String(64), index=True, doc="Identificador legible y estable, p. ej. 'al-espectro-01'."
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    hash_contenido: Mapped[str] = mapped_column(String(64), index=True)

    titulo: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(64), index=True)
    subtema: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dificultad_declarada: Mapped[int] = mapped_column(Integer, default=3)

    enunciado_publico: Mapped[str] = mapped_column(Text)
    dato_a: Mapped[str] = mapped_column(Text)
    dato_b: Mapped[str] = mapped_column(Text)

    respuesta_canonica: Mapped[str] = mapped_column(
        Text, doc="Clave contra la cual se verifica simbólicamente toda respuesta."
    )
    tipo_respuesta: Mapped[str] = mapped_column(String(20), default="expresion")
    resolucion_latex: Mapped[str] = mapped_column(Text)

    estructura_solucion: Mapped[dict] = mapped_column(
        JSON, default=dict, doc="DAG anotado: pasos, lados y dependencias."
    )

    activa: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    creada_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)

    mediciones: Mapped[list[MedicionDiseno]] = relationship(
        back_populates="instancia", cascade="all, delete-orphan"
    )
    episodios: Mapped[list[Episodio]] = relationship(back_populates="instancia")


class EjecucionSolver(Base):
    """Una ejecución individual del solver de referencia sobre una celda.

    Se guarda cada ejecución y no sólo el agregado, porque el agregado se puede
    recalcular pero la ejecución no se puede recuperar, y porque inspeccionar
    los casos en que el solver acierta con un solo dato es la forma de detectar
    contaminación del corpus de entrenamiento.
    """

    __tablename__ = "ejecuciones_solver"
    __table_args__ = (Index("ix_ejecuciones_instancia_celda", "instancia_id", "celda"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instancia_id: Mapped[int] = mapped_column(ForeignKey("instancias.id"), index=True)

    celda: Mapped[str] = mapped_column(String(16))
    indice_replica: Mapped[int] = mapped_column(Integer)

    modelo: Mapped[str] = mapped_column(String(64))
    esfuerzo: Mapped[str] = mapped_column(String(16))
    huella_experimental: Mapped[str] = mapped_column(String(32), index=True)

    respuesta_cruda: Mapped[str] = mapped_column(Text)
    respuesta_extraida: Mapped[str | None] = mapped_column(Text, nullable=True)
    veredicto: Mapped[str] = mapped_column(String(20), index=True)
    acerto: Mapped[bool] = mapped_column(Boolean, index=True)

    tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_salida: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ejecutada_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)


class MedicionDiseno(Base):
    """Perfil de diseño calculado para una instancia bajo una huella dada.

    Hay una fila por combinación de instancia y huella experimental: cambiar el
    solver de referencia produce otra medición, no sobrescribe la anterior.
    """

    __tablename__ = "mediciones_diseno"
    __table_args__ = (
        UniqueConstraint("instancia_id", "huella_experimental", name="instancia_huella"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instancia_id: Mapped[int] = mapped_column(ForeignKey("instancias.id"), index=True)
    huella_experimental: Mapped[str] = mapped_column(String(32), index=True)
    hash_contenido: Mapped[str] = mapped_column(
        String(64), doc="Contenido de la instancia al momento de medir."
    )

    v_vacia: Mapped[float] = mapped_column(Float)
    v_solo_a: Mapped[float] = mapped_column(Float)
    v_solo_b: Mapped[float] = mapped_column(Float)
    v_ambos: Mapped[float] = mapped_column(Float)
    ensayos_por_celda: Mapped[int] = mapped_column(Integer)

    interdependencia: Mapped[float] = mapped_column(Float, index=True)
    balance_carga: Mapped[float] = mapped_column(Float)
    emergencia: Mapped[float] = mapped_column(Float)
    rondas_minimas: Mapped[int] = mapped_column(Integer)
    dificultad: Mapped[float] = mapped_column(Float)

    error_estandar_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    monotonia_violada: Mapped[bool] = mapped_column(Boolean, default=False)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)

    calculada_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)

    instancia: Mapped[Instancia] = relationship(back_populates="mediciones")


# ---------------------------------------------------------------------------
# Episodios
# ---------------------------------------------------------------------------


class Episodio(Base):
    """Un intento de resolución bajo una modalidad y una condición.

    Es la unidad de observación del estudio. Todo lo que puede afectar el
    resultado —modalidad, condición, lado asignado, modelo, semilla— se registra
    en la fila, de modo que el episodio se pueda reconstruir sin consultar la
    configuración vigente al momento de correrlo.
    """

    __tablename__ = "episodios"
    __table_args__ = (
        Index("ix_episodios_instancia_modalidad", "instancia_id", "modalidad"),
        Index("ix_episodios_analisis", "modalidad", "condicion_divulgacion", "estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"), index=True)
    instancia_id: Mapped[int] = mapped_column(ForeignKey("instancias.id"), index=True)

    modalidad: Mapped[str] = mapped_column(String(32), index=True)
    condicion_divulgacion: Mapped[str] = mapped_column(
        String(16), default=CondicionDivulgacion.LIBRE
    )
    lado_humano: Mapped[str | None] = mapped_column(
        String(4), nullable=True, doc="Contrabalanceo del rol. Nulo en agente-agente."
    )

    modelo_participante: Mapped[str] = mapped_column(String(64))
    esfuerzo_participante: Mapped[str] = mapped_column(String(16))
    huella_experimental: Mapped[str] = mapped_column(String(32), index=True)
    semilla: Mapped[int] = mapped_column(Integer)
    simulado: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        doc="Episodio generado sin credencial de modelo. No es dato experimental.",
    )

    estado: Mapped[str] = mapped_column(String(20), default=EstadoEpisodio.EN_CURSO, index=True)
    turnos_usados: Mapped[int] = mapped_column(Integer, default=0)

    respuesta_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    veredicto: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    acerto: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)

    turno_divulgacion_a: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Turno en que el dato de A quedó recuperable del transcript."
    )
    turno_divulgacion_b: Mapped[int | None] = mapped_column(Integer, nullable=True)

    iniciado_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)
    finalizado_en: Mapped[datetime | None] = mapped_column(MarcaTemporal, nullable=True)

    cuenta: Mapped[Cuenta] = relationship(back_populates="episodios")
    instancia: Mapped[Instancia] = relationship(back_populates="episodios")
    turnos: Mapped[list[Turno]] = relationship(
        back_populates="episodio",
        cascade="all, delete-orphan",
        order_by="Turno.orden",
    )
    codificaciones: Mapped[list[Codificacion]] = relationship(
        back_populates="episodio", cascade="all, delete-orphan"
    )

    @property
    def esta_abierto(self) -> bool:
        return self.estado == EstadoEpisodio.EN_CURSO

    @property
    def divulgacion_prematura(self) -> bool | None:
        """``True`` si algún dato privado se volcó en el primer turno.

        Devuelve ``None`` mientras no se haya analizado la divulgación, para no
        confundir "no ocurrió" con "no se midió".
        """
        turnos = [self.turno_divulgacion_a, self.turno_divulgacion_b]
        if all(t is None for t in turnos):
            return None
        return any(t == 1 for t in turnos if t is not None)


class Turno(Base):
    """Un mensaje dentro de un episodio, con su costo y su latencia.

    El costo y la latencia no son telemetría de operación: la eficiencia es un
    indicador del perfil de episodio, y sin tokens ni tiempos no se puede
    distinguir un diálogo conciso de uno que dio vueltas.
    """

    __tablename__ = "turnos"
    __table_args__ = (UniqueConstraint("episodio_id", "orden", name="episodio_orden"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episodio_id: Mapped[int] = mapped_column(ForeignKey("episodios.id"), index=True)

    orden: Mapped[int] = mapped_column(Integer)
    rol: Mapped[str] = mapped_column(String(20))
    tipo_autor: Mapped[str] = mapped_column(String(12))
    contenido: Mapped[str] = mapped_column(Text)

    tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_salida: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    creado_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)

    episodio: Mapped[Episodio] = relationship(back_populates="turnos")


class Codificacion(Base):
    """Codificación de la calidad del proceso de un episodio.

    Puede haber varias por episodio: una por cada juez, más las humanas de la
    submuestra de validación. El acuerdo entre ellas es lo que sostiene la
    validez de la codificación automática, así que conviven en la misma tabla y
    se distinguen por ``codificador``.
    """

    __tablename__ = "codificaciones"
    __table_args__ = (
        UniqueConstraint("episodio_id", "codificador", "pasada", name="episodio_codificador"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episodio_id: Mapped[int] = mapped_column(ForeignKey("episodios.id"), index=True)

    codificador: Mapped[str] = mapped_column(
        String(64), index=True, doc="Modelo juez, o seudónimo del anotador humano."
    )
    es_humano: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pasada: Mapped[int] = mapped_column(Integer, default=1)

    puntajes: Mapped[dict] = mapped_column(JSON, doc="Las doce celdas, código -> 0..3.")
    indice_calidad: Mapped[float] = mapped_column(Float, index=True)

    modalidad_adivinada: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc=(
            "Prueba de desenmascaramiento: qué modalidad cree el juez que "
            "observó. Si acierta por encima del azar, la ceguera falló."
        ),
    )
    justificacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_salida: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codificada_en: Mapped[datetime] = mapped_column(MarcaTemporal, default=ahora)

    episodio: Mapped[Episodio] = relationship(back_populates="codificaciones")
