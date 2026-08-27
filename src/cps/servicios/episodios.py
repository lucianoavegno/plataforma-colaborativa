"""Orquestación de episodios: crear, avanzar y cerrar.

Concentra las reglas que no pertenecen ni al dominio puro ni al transporte HTTP:
qué dato ve cada participante, cuándo se puede avanzar un turno, y cómo se cierra
un episodio con verificación de la respuesta.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cps.agentes.dialogo import (
    TurnoDialogo,
    responder_como,
    siguiente_en_hablar,
)
from cps.agentes.motor import MotorModelos
from cps.config import Configuracion
from cps.dominio.areas import nombre_area
from cps.dominio.verificacion import TipoRespuesta, verificar
from cps.modelos.base import ahora
from cps.modelos.entidades import (
    CondicionDivulgacion,
    Cuenta,
    Episodio,
    EstadoEpisodio,
    Instancia,
    LadoAsignado,
    Modalidad,
    RolTurno,
    TipoAutor,
    Turno,
)
from cps.servicios.aleatorizacion import asignar_condicion

__all__ = [
    "ErrorDeEpisodio",
    "avanzar_dialogo_agentes",
    "cerrar_con_respuesta",
    "crear_episodio",
    "dato_para_humano",
    "historial_de",
    "responder_a_humano",
]


class ErrorDeEpisodio(RuntimeError):
    """Operación inválida sobre un episodio."""


@dataclass(frozen=True, slots=True)
class TurnoRegistrado:
    rol: str
    contenido: str
    tipo_autor: str
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    latencia_ms: int | None = None


def historial_de(episodio: Episodio) -> list[TurnoDialogo]:
    """Transcript del episodio en la forma que consume la capa de agentes."""
    return [TurnoDialogo(rol=t.rol, contenido=t.contenido) for t in episodio.turnos]


def dato_para_humano(episodio: Episodio) -> str | None:
    """El dato privado que le corresponde al participante humano.

    Devuelve ``None`` en agente-agente: ahí no hay humano dentro del episodio, y
    exponer cualquiera de los dos datos permitiría al observador anticipar el
    diálogo.
    """
    if episodio.modalidad != Modalidad.AGENTE_ESTUDIANTE:
        return None
    if episodio.lado_humano == LadoAsignado.B:
        return episodio.instancia.dato_b
    return episodio.instancia.dato_a


def _dato_para_modelo(episodio: Episodio) -> str:
    """El dato del agente en agente-estudiante: siempre el complementario."""
    if episodio.lado_humano == LadoAsignado.B:
        return episodio.instancia.dato_a
    return episodio.instancia.dato_b


def _rol_del_humano(episodio: Episodio) -> str:
    return (
        RolTurno.PARTICIPANTE_B
        if episodio.lado_humano == LadoAsignado.B
        else RolTurno.PARTICIPANTE_A
    )


def _rol_del_modelo(episodio: Episodio) -> str:
    return (
        RolTurno.PARTICIPANTE_A
        if episodio.lado_humano == LadoAsignado.B
        else RolTurno.PARTICIPANTE_B
    )


def crear_episodio(
    sesion: Session,
    *,
    cuenta: Cuenta,
    instancia: Instancia,
    modalidad: Modalidad,
    config: Configuracion,
    motor: MotorModelos,
    condicion_forzada: CondicionDivulgacion | None = None,
    lado_forzado: LadoAsignado | None = None,
) -> Episodio:
    """Crea un episodio con su condición asignada y el enunciado como turno cero.

    La asignación se balancea contra los episodios ya existentes de la misma
    instancia y modalidad, de modo que las celdas del diseño factorial se
    mantengan parejas a medida que se recolecta.
    """
    condiciones_previas = _contar_por(
        sesion, Episodio.condicion_divulgacion, instancia.id, modalidad
    )
    lados_previos = _contar_por(sesion, Episodio.lado_humano, instancia.id, modalidad)

    asignacion = asignar_condicion(
        modalidad=modalidad,
        instancia_id=instancia.id,
        cuenta_id=cuenta.id,
        semilla=config.semilla_aleatorizacion,
        condiciones_previas=condiciones_previas,
        lados_previos=lados_previos,
    )

    episodio = Episodio(
        cuenta_id=cuenta.id,
        instancia_id=instancia.id,
        modalidad=modalidad,
        condicion_divulgacion=condicion_forzada or asignacion.condicion,
        lado_humano=(lado_forzado or asignacion.lado_humano),
        modelo_participante=config.modelo_participante,
        esfuerzo_participante=config.esfuerzo_participante,
        huella_experimental=config.huella_experimental(),
        semilla=asignacion.semilla_efectiva,
        simulado=motor.simulado,
        estado=EstadoEpisodio.EN_CURSO,
    )
    sesion.add(episodio)
    sesion.flush()

    sesion.add(
        Turno(
            episodio_id=episodio.id,
            orden=0,
            rol=RolTurno.SISTEMA,
            tipo_autor=TipoAutor.SISTEMA,
            contenido=instancia.enunciado_publico,
        )
    )
    episodio.turnos_usados = 0
    sesion.flush()
    sesion.refresh(episodio)
    return episodio


def _contar_por(
    sesion: Session, columna, instancia_id: int, modalidad: Modalidad
) -> dict[str, int]:
    filas = sesion.execute(
        select(columna, func.count(Episodio.id))
        .where(Episodio.instancia_id == instancia_id, Episodio.modalidad == modalidad)
        .group_by(columna)
    ).all()
    return {str(valor): cantidad for valor, cantidad in filas if valor is not None}


def _registrar(sesion: Session, episodio: Episodio, turnos: list[TurnoRegistrado]) -> None:
    """Persiste turnos nuevos manteniendo el orden y el conteo consistentes."""
    orden = len(episodio.turnos)
    for turno in turnos:
        sesion.add(
            Turno(
                episodio_id=episodio.id,
                orden=orden,
                rol=turno.rol,
                tipo_autor=turno.tipo_autor,
                contenido=turno.contenido,
                tokens_entrada=turno.tokens_entrada,
                tokens_salida=turno.tokens_salida,
                latencia_ms=turno.latencia_ms,
            )
        )
        orden += 1

    # El turno cero es el enunciado, que no cuenta como intercambio.
    episodio.turnos_usados = max(0, orden - 1)


def avanzar_dialogo_agentes(
    sesion: Session,
    episodio: Episodio,
    *,
    turnos: int,
    motor: MotorModelos,
    config: Configuracion,
) -> list[TurnoRegistrado]:
    """Corre una tanda de turnos alternados entre los dos agentes."""
    if episodio.modalidad != Modalidad.AGENTE_AGENTE:
        raise ErrorDeEpisodio("Este episodio no es de la modalidad agente-agente")
    if not episodio.esta_abierto:
        raise ErrorDeEpisodio("El episodio ya está cerrado")

    instancia = episodio.instancia
    area = nombre_area(instancia.area)
    restringida = episodio.condicion_divulgacion == CondicionDivulgacion.RESTRINGIDA

    historial = historial_de(episodio)
    rol = siguiente_en_hablar(historial)
    nuevos: list[TurnoRegistrado] = []

    disponibles = max(0, config.max_turnos_episodio - episodio.turnos_usados)
    for _ in range(min(turnos, disponibles)):
        dato = instancia.dato_a if rol == RolTurno.PARTICIPANTE_A else instancia.dato_b
        respuesta = responder_como(
            motor=motor,
            rol=rol,
            area=area,
            enunciado_publico=instancia.enunciado_publico,
            dato_propio=dato,
            historial=historial,
            divulgacion_restringida=restringida,
            interlocutor_humano=False,
            modelo=config.modelo_participante,
            esfuerzo=config.esfuerzo_participante,
        )

        texto = respuesta.texto or "_(sin contenido)_"
        registrado = TurnoRegistrado(
            rol=rol,
            contenido=texto,
            tipo_autor=TipoAutor.MODELO,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            latencia_ms=respuesta.latencia_ms,
        )
        nuevos.append(registrado)
        historial.append(TurnoDialogo(rol=rol, contenido=texto))
        rol = siguiente_en_hablar(historial)

    _registrar(sesion, episodio, nuevos)

    if episodio.turnos_usados >= config.max_turnos_episodio:
        episodio.estado = EstadoEpisodio.ABANDONADO
        episodio.finalizado_en = ahora()

    return nuevos


def responder_a_humano(
    sesion: Session,
    episodio: Episodio,
    *,
    mensaje: str,
    motor: MotorModelos,
    config: Configuracion,
) -> TurnoRegistrado:
    """Registra el turno del estudiante y produce la respuesta del agente."""
    if episodio.modalidad != Modalidad.AGENTE_ESTUDIANTE:
        raise ErrorDeEpisodio("Este episodio no es de la modalidad agente-estudiante")
    if not episodio.esta_abierto:
        raise ErrorDeEpisodio("El episodio ya está cerrado")
    if episodio.turnos_usados >= config.max_turnos_episodio:
        raise ErrorDeEpisodio("Se alcanzó el máximo de turnos del episodio")

    instancia = episodio.instancia
    rol_humano = _rol_del_humano(episodio)
    rol_modelo = _rol_del_modelo(episodio)

    historial = historial_de(episodio)
    historial.append(TurnoDialogo(rol=rol_humano, contenido=mensaje))

    respuesta = responder_como(
        motor=motor,
        rol=rol_modelo,
        area=nombre_area(instancia.area),
        enunciado_publico=instancia.enunciado_publico,
        dato_propio=_dato_para_modelo(episodio),
        historial=historial,
        divulgacion_restringida=(
            episodio.condicion_divulgacion == CondicionDivulgacion.RESTRINGIDA
        ),
        interlocutor_humano=True,
        modelo=config.modelo_participante,
        esfuerzo=config.esfuerzo_participante,
    )

    texto = respuesta.texto or "_(sin contenido)_"
    turno_modelo = TurnoRegistrado(
        rol=rol_modelo,
        contenido=texto,
        tipo_autor=TipoAutor.MODELO,
        tokens_entrada=respuesta.tokens_entrada,
        tokens_salida=respuesta.tokens_salida,
        latencia_ms=respuesta.latencia_ms,
    )

    _registrar(
        sesion,
        episodio,
        [
            TurnoRegistrado(rol=rol_humano, contenido=mensaje, tipo_autor=TipoAutor.HUMANO),
            turno_modelo,
        ],
    )
    return turno_modelo


def cerrar_con_respuesta(
    sesion: Session, episodio: Episodio, *, respuesta: str
) -> tuple[str, bool, str | None]:
    """Cierra el episodio verificando la respuesta contra la clave canónica.

    Es el único camino por el cual un episodio queda marcado como acertado. No
    hay detección de marcadores en el texto del diálogo: si la corrección
    dependiera de que el participante escriba una palabra, se estaría midiendo su
    disposición a declararse exitoso y no su acierto.

    Returns
    -------
    ``(veredicto, acerto, forma_normalizada)``.
    """
    if not episodio.esta_abierto:
        raise ErrorDeEpisodio("El episodio ya está cerrado")

    instancia = episodio.instancia
    resultado = verificar(
        respuesta,
        instancia.respuesta_canonica,
        TipoRespuesta(instancia.tipo_respuesta),
    )

    episodio.respuesta_final = respuesta
    episodio.veredicto = resultado.veredicto
    episodio.acerto = resultado.es_correcto
    episodio.estado = EstadoEpisodio.FINALIZADO
    episodio.finalizado_en = ahora()

    return resultado.veredicto, resultado.es_correcto, resultado.forma_normalizada


def abandonar(sesion: Session, episodio: Episodio) -> None:
    """Cierra un episodio sin respuesta. Es dato faltante, no fracaso."""
    if not episodio.esta_abierto:
        return
    episodio.estado = EstadoEpisodio.ABANDONADO
    episodio.finalizado_en = ahora()
