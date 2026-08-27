"""Cliente de modelos, con contabilidad de costo y modo simulado.

Toda llamada devuelve una :class:`Respuesta` con tokens y latencia además del
texto. No es telemetría: la eficiencia es un indicador del perfil de episodio, y
sin el costo de cada turno no se puede distinguir un diálogo conciso de uno que
llegó al mismo resultado dando vueltas.

Sin credencial, el motor responde de forma determinista. Ese modo sirve para
desarrollar y para probar el circuito completo sin gastar, pero los episodios
que produce quedan marcados con ``simulado=True`` y deben excluirse de todo
análisis.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from cps.config import Configuracion, obtener_config

__all__ = ["Mensaje", "MotorModelos", "Respuesta", "obtener_motor"]


@dataclass(frozen=True, slots=True)
class Mensaje:
    """Un mensaje en el formato que espera la API de conversación."""

    rol: str  # "user" | "assistant"
    contenido: str

    def como_dict(self) -> dict[str, str]:
        return {"role": self.rol, "content": self.contenido}


@dataclass(frozen=True, slots=True)
class Respuesta:
    """Texto devuelto por el modelo junto con lo que costó obtenerlo."""

    texto: str
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    latencia_ms: int | None = None
    modelo: str = ""
    rechazada: bool = False
    """El modelo declinó responder. Se distingue de una respuesta vacía porque
    en el análisis es dato faltante y no un turno improductivo."""

    metadatos: dict[str, Any] = field(default_factory=dict)


class ErrorDeModelo(RuntimeError):
    """La llamada al modelo falló de forma no recuperable."""


class MotorModelos:
    """Envoltorio sobre la API de modelos con reintento y fallback simulado."""

    def __init__(self, config: Configuracion | None = None) -> None:
        self._config = config or obtener_config()
        self._cliente: Any = None
        self.simulado = not self._config.modelos_reales_disponibles

        if not self.simulado:
            try:
                from anthropic import Anthropic

                self._cliente = Anthropic(api_key=self._config.anthropic_api_key)
            except Exception as exc:
                self.simulado = True
                self._motivo_simulacion = f"No se pudo inicializar el cliente: {exc}"
        if self.simulado and not hasattr(self, "_motivo_simulacion"):
            self._motivo_simulacion = "No hay ANTHROPIC_API_KEY configurada"

    @property
    def motivo_simulacion(self) -> str | None:
        return self._motivo_simulacion if self.simulado else None

    def completar(
        self,
        *,
        sistema: str,
        mensajes: list[Mensaje],
        modelo: str | None = None,
        esfuerzo: str | None = None,
        max_tokens: int | None = None,
        reintentos: int = 2,
    ) -> Respuesta:
        """Una llamada de completado, midiendo tiempo y tokens.

        Los reintentos son sólo para fallos transitorios de red. Un rechazo del
        modelo no se reintenta: es una respuesta legítima que hay que registrar.
        """
        modelo_efectivo = modelo or self._config.modelo_participante

        if self.simulado:
            return _completar_simulado(sistema, mensajes, modelo_efectivo)

        comienzo = time.perf_counter()
        respuesta = self._llamar_con_reintentos(
            modelo=modelo_efectivo,
            sistema=sistema,
            mensajes=mensajes,
            esfuerzo=esfuerzo or self._config.esfuerzo_participante,
            max_tokens=max_tokens or self._config.max_tokens_respuesta,
            reintentos=reintentos,
        )
        latencia_ms = int((time.perf_counter() - comienzo) * 1000)

        if getattr(respuesta, "stop_reason", None) == "refusal":
            return Respuesta(
                texto="",
                latencia_ms=latencia_ms,
                modelo=modelo_efectivo,
                rechazada=True,
            )

        partes = [b.text for b in respuesta.content if getattr(b, "type", None) == "text"]
        uso = getattr(respuesta, "usage", None)

        return Respuesta(
            texto="\n".join(p for p in partes if p).strip(),
            tokens_entrada=getattr(uso, "input_tokens", None) if uso else None,
            tokens_salida=getattr(uso, "output_tokens", None) if uso else None,
            latencia_ms=latencia_ms,
            modelo=modelo_efectivo,
            metadatos={"stop_reason": getattr(respuesta, "stop_reason", None)},
        )

    def _llamar_con_reintentos(
        self,
        *,
        modelo: str,
        sistema: str,
        mensajes: list[Mensaje],
        esfuerzo: str,
        max_tokens: int,
        reintentos: int,
    ) -> Any:
        """Llama a la API con retroceso exponencial ante fallos transitorios.

        Un rechazo del modelo no llega acá: es una respuesta válida de la API y
        se interpreta más arriba. Lo que se reintenta son errores de transporte
        y límites de tasa.
        """
        for intento in range(reintentos + 1):
            try:
                return self._cliente.messages.create(
                    model=modelo,
                    max_tokens=max_tokens,
                    output_config={"effort": esfuerzo},
                    system=sistema,
                    messages=[m.como_dict() for m in mensajes],
                )
            except Exception as exc:
                if intento == reintentos:
                    raise ErrorDeModelo(
                        f"Falló la llamada a {modelo} tras {reintentos + 1} intentos: {exc}"
                    ) from exc
                time.sleep(2.0**intento)

        raise ErrorDeModelo("Estado inalcanzable en el bucle de reintentos")

    def completar_json(
        self,
        *,
        sistema: str,
        mensajes: list[Mensaje],
        modelo: str | None = None,
        esfuerzo: str | None = None,
    ) -> tuple[dict[str, Any] | None, Respuesta]:
        """Completado que además intenta interpretar la respuesta como JSON.

        Devuelve ``(None, respuesta)`` si no se pudo extraer un objeto válido, y
        deja la respuesta cruda disponible para inspección: un fallo de formato
        del juez es un dato sobre el juez y conviene poder revisarlo.
        """
        respuesta = self.completar(
            sistema=sistema, mensajes=mensajes, modelo=modelo, esfuerzo=esfuerzo
        )
        return _extraer_json(respuesta.texto), respuesta


def _extraer_json(texto: str) -> dict[str, Any] | None:
    """Recupera el primer objeto JSON del texto, tolerando cercos de markdown."""
    if not texto:
        return None

    sin_cerco = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.MULTILINE)

    try:
        cargado = json.loads(sin_cerco)
        return cargado if isinstance(cargado, dict) else None
    except json.JSONDecodeError:
        pass

    inicio = sin_cerco.find("{")
    fin = sin_cerco.rfind("}")
    if inicio == -1 or fin <= inicio:
        return None
    try:
        cargado = json.loads(sin_cerco[inicio : fin + 1])
        return cargado if isinstance(cargado, dict) else None
    except json.JSONDecodeError:
        return None


def _completar_simulado(sistema: str, mensajes: list[Mensaje], modelo: str) -> Respuesta:
    """Respuesta determinista, derivada del prompt por hash.

    Es deliberadamente reconocible: empieza avisando que es simulada, para que
    ningún transcript de este modo pueda confundirse con dato experimental
    aunque se lo mire fuera de contexto.
    """
    semilla = int(hashlib.sha256((sistema + str(len(mensajes))).encode()).hexdigest()[:8], 16)

    if "Resolvé el siguiente problema" in sistema:
        # Solver de referencia: responde algo determinista pero casi siempre
        # equivocado, de modo que el circuito completo se pueda ejercitar.
        return Respuesta(
            texto=f"Desarrollo simulado.\n\n[RESUELTO] {semilla % 97}",
            tokens_entrada=len(sistema) // 4,
            tokens_salida=12,
            latencia_ms=1,
            modelo=modelo,
            metadatos={"simulado": True},
        )

    if "codificador experto" in sistema:
        from cps.dominio.rubrica import CELDAS

        puntajes = {c.codigo: (semilla >> i) % 4 for i, c in enumerate(CELDAS)}
        cuerpo = json.dumps(
            {
                "puntajes": puntajes,
                "modalidad_adivinada": "no_se",
                "justificacion": "Codificación simulada, sin valor experimental.",
            },
            ensure_ascii=False,
        )
        return Respuesta(texto=cuerpo, latencia_ms=1, modelo=modelo, metadatos={"simulado": True})

    if "recuperable" in sistema:
        return Respuesta(
            texto=json.dumps({"turno": None}), latencia_ms=1, modelo=modelo,
            metadatos={"simulado": True},
        )

    dato = _extraer_dato_privado(sistema)
    intercambios = sum(1 for m in mensajes if m.rol == "user")

    if intercambios <= 1:
        texto = (
            "*(modo simulado: sin credencial de modelo, este turno no es dato "
            "experimental)*\n\nMi dato privado es:\n\n"
            f"{dato}\n\nCon esto solo no alcanza. ¿Me pasás el tuyo?"
        )
    else:
        texto = (
            "*(modo simulado)*\n\nCombinando ambos datos queda determinado el "
            "sistema. Para ver el desarrollo completo, consultá la resolución."
        )

    return Respuesta(
        texto=texto,
        tokens_entrada=len(sistema) // 4,
        tokens_salida=len(texto) // 4,
        latencia_ms=1,
        modelo=modelo,
        metadatos={"simulado": True},
    )


def _extraer_dato_privado(sistema: str) -> str:
    """Recupera el dato privado del prompt, para que la simulación sea coherente."""
    marcador = "TU DATO PRIVADO"
    if marcador not in sistema:
        return "(sin dato)"
    resto = sistema.split(marcador, 1)[1]
    cuerpo = resto.split("\n", 1)[1] if "\n" in resto else resto
    return cuerpo.split("\n\nTu interlocutor")[0].strip()


_motor_singleton: MotorModelos | None = None


def obtener_motor() -> MotorModelos:
    """Motor compartido del proceso."""
    global _motor_singleton
    if _motor_singleton is None:
        _motor_singleton = MotorModelos()
    return _motor_singleton
