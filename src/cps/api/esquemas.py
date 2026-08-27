"""Esquemas de entrada y salida de la API.

La responsabilidad crítica de este módulo es la frontera entre lo público y lo
privado de una instancia. Los datos ``dato_a``, ``dato_b``, ``respuesta_canonica``
y ``resolucion_latex`` no aparecen en ningún esquema de catálogo. Salen del
sistema únicamente por tres vías, todas explícitas:

* el dato que corresponde al participante en su propio episodio;
* la resolución, cuando alguien la pide a sabiendas de que queda registrado;
* la exportación para investigadores.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from cps.modelos.entidades import CondicionDivulgacion, LadoAsignado, Modalidad

ORM = ConfigDict(from_attributes=True)


# --- Cuentas ---------------------------------------------------------------


class CuentaCrear(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    acepta_consentimiento: bool = Field(
        description="Debe ser verdadero: sin consentimiento no se crean episodios."
    )

    @field_validator("acepta_consentimiento")
    @classmethod
    def _exigir_consentimiento(cls, valor: bool) -> bool:
        if not valor:
            raise ValueError(
                "Es necesario aceptar el consentimiento informado para participar."
            )
        return valor


class CuentaLogin(BaseModel):
    email: EmailStr
    password: str


class CuentaSalida(BaseModel):
    id: int
    email: EmailStr
    nombre: str
    rol: str
    seudonimo: str
    creada_en: datetime | None = None

    model_config = ORM


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cuenta: CuentaSalida


class TextoConsentimiento(BaseModel):
    version: str
    hash: str
    cuerpo: str


# --- Catálogo --------------------------------------------------------------


class AreaSalida(BaseModel):
    clave: str
    nombre: str
    cantidad_instancias: int = 0


class PerfilDisenoSalida(BaseModel):
    """Indicadores de diseño. No incluye las competencias crudas por celda.

    Publicar ``v({d_a})`` en el catálogo revelaría cuánto aporta cada dato, que
    es información sobre la partición. Los valores crudos están en la
    exportación para investigadores.
    """

    interdependencia: float
    balance_carga: float
    emergencia: float
    rondas_minimas: int
    dificultad: float
    nivel: str
    monotonia_violada: bool
    calculada_en: datetime | None = None

    model_config = ORM


class InstanciaResumen(BaseModel):
    """Lo que ve el catálogo. Nunca incluye datos privados ni resolución."""

    id: int
    codigo: str
    version: int
    titulo: str
    area: str
    area_nombre: str
    subtema: str | None = None
    dificultad_declarada: int
    perfil: PerfilDisenoSalida | None = None

    model_config = ORM


class InstanciaDetalle(InstanciaResumen):
    enunciado_publico: str


class ResolucionSalida(BaseModel):
    """Resolución completa. Su consulta queda registrada como episodio."""

    instancia_id: int
    enunciado_publico: str
    dato_a: str
    dato_b: str
    resolucion_latex: str
    respuesta_canonica: str


# --- Episodios -------------------------------------------------------------


class EpisodioCrear(BaseModel):
    instancia_id: int
    modalidad: Modalidad
    condicion_divulgacion: CondicionDivulgacion | None = Field(
        default=None,
        description=(
            "Si se omite, la asigna el sistema por aleatorización registrada. "
            "Fijarla a mano requiere rol de investigador."
        ),
    )
    lado_humano: LadoAsignado | None = Field(
        default=None,
        description=(
            "Contrabalanceo del rol. Si se omite, lo asigna el sistema. "
            "Sólo aplica a la modalidad agente-estudiante."
        ),
    )


class TurnoSalida(BaseModel):
    id: int
    orden: int
    rol: str
    tipo_autor: str
    contenido: str
    creado_en: datetime | None = None

    model_config = ORM


class EpisodioResumen(BaseModel):
    id: int
    instancia_id: int
    instancia_titulo: str | None = None
    area_nombre: str | None = None
    modalidad: str
    condicion_divulgacion: str
    lado_humano: str | None = None
    estado: str
    turnos_usados: int
    acerto: bool | None = None
    veredicto: str | None = None
    simulado: bool = False
    iniciado_en: datetime | None = None
    finalizado_en: datetime | None = None

    model_config = ORM


class EpisodioDetalle(EpisodioResumen):
    turnos: list[TurnoSalida] = Field(default_factory=list)
    dato_asignado: str | None = Field(
        default=None,
        description="El dato privado que le toca al participante humano, si aplica.",
    )
    enunciado_publico: str | None = None


class MensajeEntrada(BaseModel):
    contenido: str = Field(min_length=1, max_length=8000)


class EjecutarTanda(BaseModel):
    turnos: int = Field(default=4, ge=1, le=12)


class RespuestaFinal(BaseModel):
    """Cierre explícito de un episodio con la respuesta del participante.

    Existe como endpoint aparte, y no como detección de un marcador en el texto,
    porque la corrección debe verificarse contra la clave canónica y no depender
    de que el participante declare haber acertado.
    """

    respuesta: str = Field(min_length=1, max_length=2000)


class ResultadoVerificacion(BaseModel):
    veredicto: str
    acerto: bool
    respuesta_registrada: str
    forma_normalizada: str | None = None


# --- Investigación ---------------------------------------------------------


class InstanciaCrear(BaseModel):
    codigo: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9-]+$")
    titulo: str = Field(min_length=3, max_length=200)
    area: str
    subtema: str | None = None
    dificultad_declarada: int = Field(default=3, ge=1, le=5)
    enunciado_publico: str = Field(min_length=10)
    dato_a: str = Field(min_length=1)
    dato_b: str = Field(min_length=1)
    respuesta_canonica: str = Field(min_length=1)
    tipo_respuesta: str = "expresion"
    resolucion_latex: str = Field(min_length=10)
    estructura_solucion: dict = Field(default_factory=dict)


class ResumenBanco(BaseModel):
    """Estado del banco desde el punto de vista del protocolo."""

    total_instancias: int
    calibradas: int
    sin_calibrar: int
    cumplen_criterio: int
    con_advertencias: int
    episodios_por_modalidad: dict[str, int]
    episodios_simulados: int
    huella_experimental: str


class EstadoSistema(BaseModel):
    version_protocolo: str
    huella_experimental: str
    modelos_simulados: bool
    motivo_simulacion: str | None = None
    modalidades: list[str]
