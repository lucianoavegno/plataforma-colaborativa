"""Agentes: motor de modelos, protocolo, diálogo, solver de referencia y jueces."""

from cps.agentes.motor import ErrorDeModelo, Mensaje, MotorModelos, Respuesta, obtener_motor
from cps.agentes.protocolo import MARCA_FIN, VERSION_PROTOCOLO

__all__ = [
    "MARCA_FIN",
    "VERSION_PROTOCOLO",
    "ErrorDeModelo",
    "Mensaje",
    "MotorModelos",
    "Respuesta",
    "obtener_motor",
]
