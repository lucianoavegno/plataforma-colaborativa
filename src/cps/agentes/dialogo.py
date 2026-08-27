"""Conducción de un episodio de diálogo con información asimétrica.

La pieza central es :func:`vista_desde`, que reproyecta un único transcript a la
perspectiva de cada participante. La conversación se guarda una sola vez, pero
cada participante la ve con los roles invertidos: lo propio como ``assistant`` y
lo ajeno como ``user``. Eso permite que dos "cabezas" con información distinta
compartan un mismo hilo sin que ninguna vea el dato de la otra.
"""

from __future__ import annotations

from dataclasses import dataclass

from cps.agentes.motor import Mensaje, MotorModelos, Respuesta
from cps.agentes.protocolo import RolProtocolo, prompt_participante
from cps.modelos.entidades import RolTurno

__all__ = ["TurnoDialogo", "responder_como", "vista_desde"]

# Turnos sintéticos que se inyectan cuando el historial no arranca o no termina
# donde la API lo exige. Se marcan como sintéticos para no confundirlos con
# contenido producido por los participantes.
ARRANQUE = "Empezá vos: presentá lo que sabés y tu lectura inicial del problema."
CONTINUACION = "Seguí desde donde quedaste."


@dataclass(frozen=True, slots=True)
class TurnoDialogo:
    """Un turno del transcript, independiente de la persistencia."""

    rol: str
    contenido: str


def vista_desde(rol_propio: str, historial: list[TurnoDialogo]) -> list[Mensaje]:
    """Reproyecta el transcript a la perspectiva de un participante.

    Los turnos del propio participante pasan a ``assistant`` y los de la
    contraparte a ``user``. Los turnos de sistema —el enunciado común— se
    excluyen, porque ya están en el prompt de sistema de cada participante y
    repetirlos sesgaría el contexto.

    Se agregan turnos sintéticos si hace falta, porque la API exige que la
    secuencia empiece por ``user`` y no termine en ``assistant``.
    """
    mensajes = [
        Mensaje(
            rol="assistant" if turno.rol == rol_propio else "user",
            contenido=turno.contenido,
        )
        for turno in historial
        if turno.rol != RolTurno.SISTEMA
    ]

    if not mensajes or mensajes[0].rol != "user":
        mensajes.insert(0, Mensaje(rol="user", contenido=ARRANQUE))

    if mensajes[-1].rol == "assistant":
        mensajes.append(Mensaje(rol="user", contenido=CONTINUACION))

    return mensajes


def responder_como(
    *,
    motor: MotorModelos,
    rol: str,
    area: str,
    enunciado_publico: str,
    dato_propio: str,
    historial: list[TurnoDialogo],
    divulgacion_restringida: bool,
    interlocutor_humano: bool,
    modelo: str | None = None,
    esfuerzo: str | None = None,
) -> Respuesta:
    """Produce el siguiente turno de un participante artificial."""
    plantilla = prompt_participante(
        area=area,
        enunciado_publico=enunciado_publico,
        dato_propio=dato_propio,
        rol=RolProtocolo.A if rol == RolTurno.PARTICIPANTE_A else RolProtocolo.B,
        divulgacion_restringida=divulgacion_restringida,
        interlocutor_humano=interlocutor_humano,
    )
    return motor.completar(
        sistema=plantilla.texto,
        mensajes=vista_desde(rol, historial),
        modelo=modelo,
        esfuerzo=esfuerzo,
    )


def rol_opuesto(rol: str) -> str:
    """El otro participante."""
    return (
        RolTurno.PARTICIPANTE_B
        if rol == RolTurno.PARTICIPANTE_A
        else RolTurno.PARTICIPANTE_A
    )


def siguiente_en_hablar(historial: list[TurnoDialogo]) -> str:
    """Quién habla ahora: alterna a partir de quien habló último."""
    for turno in reversed(historial):
        if turno.rol in (RolTurno.PARTICIPANTE_A, RolTurno.PARTICIPANTE_B):
            return rol_opuesto(turno.rol)
    return RolTurno.PARTICIPANTE_A


def transcripcion_numerada(historial: list[TurnoDialogo], *, anonimizar: bool = True) -> str:
    """Transcript en texto plano, numerado por turno.

    Con ``anonimizar``, los roles se reemplazan por etiquetas neutras. Es lo que
    se le pasa al juez: si los roles llevaran el nombre de la modalidad, la
    ceguera se perdería antes de empezar.
    """
    etiquetas = {
        RolTurno.PARTICIPANTE_A: "Participante 1" if anonimizar else "A",
        RolTurno.PARTICIPANTE_B: "Participante 2" if anonimizar else "B",
        RolTurno.SISTEMA: "Enunciado",
    }
    lineas = []
    numero = 0
    for turno in historial:
        if turno.rol == RolTurno.SISTEMA:
            lineas.append(f"[{etiquetas[RolTurno.SISTEMA]}]\n{turno.contenido}\n")
            continue
        numero += 1
        etiqueta = etiquetas.get(turno.rol, turno.rol)
        lineas.append(f"[Turno {numero} — {etiqueta}]\n{turno.contenido}\n")
    return "\n".join(lineas)
