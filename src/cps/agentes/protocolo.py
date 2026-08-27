"""Prompts del protocolo experimental, versionados.

Un prompt es un instrumento de medición. Si cambia, los datos obtenidos antes y
después no son comparables, y eso tiene que ser visible en los datos y no quedar
en la memoria de quien corrió el experimento. Por eso cada plantilla lleva
:data:`VERSION_PROTOCOLO`, que se registra con cada episodio y entra en la
huella experimental.

Regla de edición: cualquier cambio de contenido incrementa la versión. No se
edita una plantilla "sin querer" para arreglar una redacción.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

VERSION_PROTOCOLO: Final[str] = "2.0.0"

MARCA_FIN: Final[str] = "[RESUELTO]"


class RolProtocolo(StrEnum):
    A = "a"
    B = "b"


REGLAS_BASE: Final[str] = """\
Reglas de la interacción:
1. El problema es imposible de resolver sólo con tu dato: la otra parte tiene un
   dato distinto e imprescindible. No lo conocés y no podés adivinarlo.
2. La otra parte sólo sabe lo que vos le escribas.
3. Escribí la matemática en LaTeX: $...$ en línea y $$...$$ en bloque.
4. Sé breve: como máximo unas 150 palabras por turno.
5. Nunca inventes datos numéricos ni condiciones que no te hayan dado.
6. Cuando tengas la solución completa y la hayas verificado con la información
   de la otra parte, cerrá el mensaje con una línea que empiece exactamente con
   {marca} seguida de la respuesta final, y nada más que la respuesta final."""

# Condición experimental: prohíbe volcar el dato en el primer turno. No es una
# corrección del instrumento sino un factor cruzado, porque la restricción
# cambia el fenómeno que se observa.
REGLA_DIVULGACION_RESTRINGIDA: Final[str] = """\

7. En tu primer mensaje no compartas números, ecuaciones ni el enunciado literal
   de tu dato. Empezá preguntando y describiendo en términos generales qué tipo
   de información tenés y qué te falta."""

INSTRUCCION_CON_PERSONA: Final[str] = """\

Tu interlocutor es una persona que está resolviendo el problema. Guiá sin
resolverlo entero de una sola vez. Si te pide la respuesta final sin haber
compartido su dato, pedísela primero. No reveles pasos que dependan de
información que todavía no te dio."""


@dataclass(frozen=True, slots=True)
class Plantilla:
    """Un prompt de sistema con su procedencia registrada."""

    texto: str
    version: str = VERSION_PROTOCOLO

    @property
    def hash(self) -> str:
        """Identifica el contenido exacto, por si la versión no se incrementó."""
        return hashlib.sha256(self.texto.encode("utf-8")).hexdigest()[:16]


def prompt_participante(
    *,
    area: str,
    enunciado_publico: str,
    dato_propio: str,
    rol: RolProtocolo,
    divulgacion_restringida: bool = False,
    interlocutor_humano: bool = False,
) -> Plantilla:
    """Prompt de sistema para un participante artificial.

    Contiene el enunciado público y **sólo el dato propio**. La asimetría se
    implementa acá: no hay ninguna vía por la cual el modelo pueda acceder al
    dato de la contraparte salvo que ésta se lo escriba.
    """
    etiqueta = "Participante A" if rol is RolProtocolo.A else "Participante B"
    contraparte = "Participante B" if rol is RolProtocolo.A else "Participante A"
    if interlocutor_humano:
        contraparte = "una persona"

    reglas = REGLAS_BASE.format(marca=MARCA_FIN)
    if divulgacion_restringida:
        reglas += REGLA_DIVULGACION_RESTRINGIDA

    texto = f"""Sos el {etiqueta} en la resolución colaborativa de un problema de {area}.

ENUNCIADO COMÚN (lo conocen ambas partes):
{enunciado_publico}

TU DATO PRIVADO (la otra parte NO lo conoce):
{dato_propio}

Tu interlocutor es {contraparte} y tiene un dato privado distinto que vos desconocés.

{reglas}"""

    if interlocutor_humano:
        texto += INSTRUCCION_CON_PERSONA

    return Plantilla(texto)


def prompt_solver(*, area: str, enunciado: str, datos_disponibles: list[str]) -> Plantilla:
    """Prompt del solver de referencia sobre una celda de información.

    El solver no dialoga: recibe la información de la celda y produce una
    respuesta. Su tasa de acierto es la estimación de ``v(S)``.

    La instrucción de responder incluso sin certeza es deliberada. Si el solver
    se abstuviera ante información insuficiente, la celda individual daría cero
    por abstención y no por imposibilidad, y no se estaría midiendo la
    interdependencia sino la calibración del modelo.
    """
    if datos_disponibles:
        bloque = "\n\n".join(f"DATO {i + 1}:\n{d}" for i, d in enumerate(datos_disponibles))
        seccion = f"\n\nINFORMACIÓN ADICIONAL DISPONIBLE:\n{bloque}"
    else:
        seccion = "\n\nNo se te proporciona ninguna información adicional."

    texto = f"""Resolvé el siguiente problema de {area}.

ENUNCIADO:
{enunciado}{seccion}

Trabajá el problema y terminá con una línea que empiece exactamente con {MARCA_FIN}
seguida únicamente de la respuesta final, sin unidades ni texto adicional.

Aunque la información te parezca insuficiente, dá siempre tu mejor respuesta:
elegí la más plausible y comprometete con ella. No respondas que faltan datos."""

    return Plantilla(texto)


PROMPT_JUEZ: Final[str] = """\
Sos un codificador experto en resolución colaborativa de problemas. Vas a leer la
transcripción de un diálogo entre dos participantes que resolvían un problema de
matemática en el que cada uno tenía un dato privado distinto.

Tu tarea es puntuar doce celdas, cada una de 0 a 3. Las celdas cruzan cuatro
procesos de resolución con tres competencias colaborativas.

ESCALA (idéntica para las doce celdas):
  0 = AUSENTE: no hay evidencia de la conducta en la transcripción.
  1 = SUPERFICIAL: aparece de forma nominal, sin consecuencia sobre la resolución.
  2 = FUNCIONAL: aparece y contribuye efectivamente a avanzar.
  3 = EMERGENTE: produce entendimiento conjunto que ninguna parte traía.

CELDAS:
{celdas}

Criterios de codificación:
- Puntuá lo que está en la transcripción, no lo que suponés que los
  participantes entendieron. Sin evidencia textual, la celda es 0.
- Un turno largo no vale más que uno breve. Puntuá la contribución, no la
  extensión.
- La longitud total del diálogo no debe influir en el puntaje.
- Un intercambio donde una parte recita su dato y la otra resuelve sola no
  supera el nivel 1 en las competencias colaborativas.

Además, indicá qué tipo de participantes creés que produjeron el diálogo. Esta
pregunta es un control del procedimiento: respondé con tu impresión sincera.

Devolvé exclusivamente un objeto JSON con esta forma, sin texto alrededor:
{{"puntajes": {{"EX-CO": 0, ...las doce celdas...}},
  "modalidad_adivinada": "agente_agente" | "agente_estudiante" | "no_se",
  "justificacion": "dos o tres oraciones"}}"""


def prompt_juez() -> Plantilla:
    """Prompt del juez de codificación, con la descripción de las doce celdas."""
    from cps.dominio.rubrica import CELDAS, DESCRIPCIONES

    lineas = "\n".join(f"  {c.codigo}: {DESCRIPCIONES[c.codigo]}" for c in CELDAS)
    return Plantilla(PROMPT_JUEZ.format(celdas=lineas))


PROMPT_DIVULGACION: Final[str] = """\
Vas a leer la transcripción de un diálogo y un dato privado que uno de los
participantes tenía al empezar.

DATO PRIVADO:
{dato}

TRANSCRIPCIÓN (numerada por turno):
{transcripcion}

Indicá en qué número de turno el contenido del dato privado quedó íntegramente
recuperable a partir de la transcripción: es decir, a partir de qué turno un
lector que no conociera el dato podría reconstruirlo por completo. Que se
mencione parcialmente o se aluda a él no cuenta; tiene que quedar determinado.

Devolvé exclusivamente un objeto JSON: {{"turno": <entero o null>}}
donde null significa que nunca quedó completamente recuperable."""


def prompt_divulgacion(dato: str, transcripcion: str) -> Plantilla:
    """Prompt para localizar el turno de divulgación de un dato privado."""
    return Plantilla(PROMPT_DIVULGACION.format(dato=dato, transcripcion=transcripcion))


def normalizar_estilo(texto: str) -> str:
    """Reduce las marcas de superficie que delatan quién escribió un turno.

    La ceguera del juez respecto de la modalidad no es trivial de conseguir: los
    turnos humanos y los generados difieren en longitud, puntuación y uso de
    mayúsculas de un modo que permite identificarlos sin leer el contenido. Esta
    normalización no elimina la diferencia, pero le quita las pistas más
    groseras. El control efectivo es la pregunta de desenmascaramiento, que mide
    cuánta señal quedó.
    """
    import re

    normalizado = re.sub(r"[ \t]+", " ", texto.strip())
    normalizado = re.sub(r"\n{3,}", "\n\n", normalizado)
    normalizado = re.sub(r"([!?.])\1{1,}", r"\1", normalizado)
    return normalizado
