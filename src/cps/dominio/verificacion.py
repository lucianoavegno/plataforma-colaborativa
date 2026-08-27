"""Verificación simbólica de respuestas contra la clave canónica.

Este módulo existe para eliminar una amenaza concreta a la validez del estudio.
En la versión anterior de la plataforma, una sesión se marcaba como resuelta
cuando aparecía el token ``[RESUELTO]`` en un mensaje; en el modo con estudiante,
ese mensaje lo escribe el propio participante. Es decir, el sujeto medido podía
falsear la variable dependiente principal escribiendo una palabra. Lo que se
estaba midiendo no era el acierto sino la disposición a declararse exitoso.

Acá la corrección se decide comparando la respuesta final contra una clave
canónica registrada con la instancia, usando equivalencia simbólica y no
coincidencia textual: ``1/2``, ``0.5`` y ``\\frac{1}{2}`` son la misma respuesta,
y ``x^2-1`` es la misma que ``(x-1)(x+1)``.

El marcador de fin de diálogo sigue existiendo, pero sólo como señal de que el
participante cree haber terminado: nunca como fuente del acierto.
"""

from __future__ import annotations

import re
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import sympy
from sympy.parsing.latex import parse_latex
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    standard_transformations,
)

__all__ = ["Resultado", "TipoRespuesta", "Veredicto", "extraer_respuesta_final", "verificar"]

# Cota de tiempo para la simplificación: sympy puede colgarse en expresiones
# adversarias, y esto corre sobre entrada no confiable (texto generado).
SEGUNDOS_LIMITE: int = 5

_TRANSFORMACIONES = (
    *standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

# Marcador de fin de diálogo. Señal de intención, no de acierto.
MARCA_FIN = "[RESUELTO]"

_PATRON_RESPUESTA = re.compile(
    r"\[RESUELTO\]\s*:?\s*(.+?)(?:\n\n|\Z)", re.IGNORECASE | re.DOTALL
)


class TipoRespuesta(StrEnum):
    """Cómo debe interpretarse la clave canónica de una instancia."""

    EXPRESION = "expresion"
    """Expresión algebraica o numérica: se compara por simplificación."""

    CONJUNTO = "conjunto"
    """Conjunto de valores sin orden, separados por coma."""

    TUPLA = "tupla"
    """Secuencia ordenada de valores."""

    TEXTO = "texto"
    """Respuesta no matemática: se compara normalizada. Último recurso."""


class Veredicto(StrEnum):
    """Resultado de la verificación."""

    CORRECTO = "correcto"
    INCORRECTO = "incorrecto"
    NO_PARSEABLE = "no_parseable"
    """No se pudo interpretar la respuesta. Se distingue de INCORRECTO a
    propósito: es un fallo del instrumento, no del participante, y en el análisis
    debe tratarse como dato faltante y no como error."""

    SIN_RESPUESTA = "sin_respuesta"
    """El episodio terminó sin que se emitiera una respuesta final."""


@dataclass(frozen=True, slots=True)
class Resultado:
    """Veredicto más la traza necesaria para auditarlo."""

    veredicto: Veredicto
    respuesta_extraida: str | None
    forma_normalizada: str | None = None
    detalle: str | None = None

    @property
    def es_correcto(self) -> bool:
        return self.veredicto is Veredicto.CORRECTO

    @property
    def es_dato_faltante(self) -> bool:
        """Los casos que el análisis debe tratar como faltante, no como cero."""
        return self.veredicto in (Veredicto.NO_PARSEABLE, Veredicto.SIN_RESPUESTA)


class _TiempoAgotado(Exception):
    pass


def _puede_usar_alarma() -> bool:
    """Si ``SIGALRM`` es utilizable en el contexto de ejecución actual.

    No alcanza con que la plataforma tenga la señal: ``signal.signal`` sólo puede
    invocarse desde el hilo principal del intérprete. La API sirve sus endpoints
    síncronos en un threadpool, así que ahí la alarma no está disponible y el
    intento de instalarla lanzaría ``ValueError`` en cada verificación.
    """
    return hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()


@contextmanager
def _limite_de_tiempo(segundos: int):
    """Interrumpe una operación que exceda el presupuesto de tiempo.

    Cuando la alarma no está disponible —hilo secundario, o plataforma sin
    ``SIGALRM``— se sigue sin límite. Perder el límite es preferible a que la
    verificación falle, y el riesgo es acotado: las claves canónicas provienen de
    un banco curado y validado, y la respuesta a verificar se compara contra una
    expresión de tamaño conocido.
    """
    if not _puede_usar_alarma():
        yield
        return

    def _manejar(_signum: int, _frame: Any) -> None:
        raise _TiempoAgotado

    anterior = signal.signal(signal.SIGALRM, _manejar)
    signal.alarm(segundos)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


def extraer_respuesta_final(texto: str) -> str | None:
    """Extrae la respuesta que sigue al marcador de fin de diálogo.

    Devuelve ``None`` si el marcador no aparece o no lo sigue ningún contenido.
    """
    coincidencia = _PATRON_RESPUESTA.search(texto)
    if coincidencia is None:
        return None
    respuesta = coincidencia.group(1).strip()
    return respuesta or None


def _limpiar(expresion: str) -> str:
    """Quita el andamiaje de presentación que rodea a la respuesta.

    Los modelos envuelven la respuesta en LaTeX, la anteponen con ``x =`` o la
    encierran en delimitadores. Nada de eso hace a la respuesta.
    """
    texto = expresion.strip()
    texto = re.sub(r"^\$+|\$+$", "", texto).strip()
    texto = re.sub(r"\\[()\[\]]", "", texto).strip()
    texto = re.sub(r"^\\boxed\{(.*)\}$", r"\1", texto, flags=re.DOTALL).strip()
    texto = re.sub(r"\\(?:text|mathrm|mbox)\{[^}]*\}", "", texto).strip()
    # "p(λ) = λ^3 - 7λ^2" -> "λ^3 - 7λ^2": nos quedamos con el lado derecho.
    if texto.count("=") == 1:
        izquierda, derecha = texto.split("=")
        if len(izquierda.strip()) <= len(derecha.strip()):
            texto = derecha.strip()
    return texto.rstrip(".,;").strip()


# Nombres de símbolo que colisionan con palabras reservadas de Python y que en
# matemática universitaria aparecen todo el tiempo. Se reescriben antes de usar
# el parser de sintaxis Python y se canonizan después, para que las dos vías de
# parseo produzcan el mismo símbolo y las expresiones sean comparables.
_ALIAS_SIMBOLOS: Final[dict[str, str]] = {"lamda": "lambda"}
_RESERVADAS = {v: k for k, v in _ALIAS_SIMBOLOS.items()}


def _canonizar_simbolos(expr: sympy.Expr) -> sympy.Expr:
    """Unifica los nombres de símbolo entre la vía LaTeX y la vía Python.

    ``parse_latex(r"\\lambda")`` devuelve un símbolo llamado ``lambda``, mientras
    que la sintaxis Python obliga a escribirlo ``lamda`` porque ``lambda`` es
    palabra reservada. Sin esta normalización, la misma cantidad parseada por
    caminos distintos daría símbolos distintos y nunca compararían iguales.
    """
    sustituciones = {
        simbolo: sympy.Symbol(_ALIAS_SIMBOLOS[simbolo.name])
        for simbolo in expr.free_symbols
        if simbolo.name in _ALIAS_SIMBOLOS
    }
    return expr.subs(sustituciones) if sustituciones else expr


def _parsear(expresion: str) -> sympy.Expr:
    """Interpreta una expresión, probando primero LaTeX y luego sintaxis Python.

    El orden importa: casi todo el contenido del banco está en LaTeX, y
    ``parse_latex`` maneja fracciones y raíces que la sintaxis plana no.
    """
    limpia = _limpiar(expresion)
    if not limpia:
        raise ValueError("Expresión vacía")

    if "\\" in limpia or "^" in limpia or "_" in limpia:
        try:
            return _canonizar_simbolos(parse_latex(limpia))
        except Exception:
            pass

    for reservada, alias in _RESERVADAS.items():
        limpia = re.sub(rf"\b{reservada}\b", alias, limpia)

    return _canonizar_simbolos(
        sympy.parse_expr(limpia, transformations=_TRANSFORMACIONES, evaluate=True)
    )


def _equivalentes(a: sympy.Expr, b: sympy.Expr) -> bool:
    """Decide equivalencia simbólica entre dos expresiones.

    Se intenta primero la diferencia simplificada, que es exacta cuando cierra.
    Si no cierra —hay expresiones para las que simplificar no termina o no
    normaliza—, se cae a una comparación numérica en varios puntos, que puede dar
    falsos positivos pero cuya probabilidad es despreciable con muestreo en
    valores no especiales.
    """
    try:
        diferencia = sympy.simplify(a - b)
        if diferencia == 0:
            return True
        if diferencia.is_number:
            return bool(abs(complex(diferencia)) < 1e-9)
    except (TypeError, ValueError, AttributeError, NotImplementedError):
        pass

    libres = sorted(a.free_symbols | b.free_symbols, key=str)
    if not libres:
        try:
            return bool(abs(complex(a.evalf()) - complex(b.evalf())) < 1e-9)
        except (TypeError, ValueError):
            return False

    for desplazamiento in range(1, 6):
        sustitucion = {
            simbolo: sympy.Rational(3 + indice + 7 * desplazamiento, 5 + desplazamiento)
            for indice, simbolo in enumerate(libres)
        }
        try:
            va = complex(a.subs(sustitucion).evalf())
            vb = complex(b.subs(sustitucion).evalf())
        except (TypeError, ValueError, ZeroDivisionError):
            return False
        if abs(va - vb) > 1e-7 * max(1.0, abs(va)):
            return False
    return True


def _normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.strip().lower())


def verificar(
    respuesta: str | None,
    clave: str,
    tipo: TipoRespuesta = TipoRespuesta.EXPRESION,
) -> Resultado:
    """Compara una respuesta contra la clave canónica de la instancia.

    Parameters
    ----------
    respuesta:
        Texto de la respuesta final, ya extraído del transcript. ``None`` o
        vacío produce :attr:`Veredicto.SIN_RESPUESTA`.
    clave:
        Respuesta canónica registrada con la instancia.
    tipo:
        Cómo interpretar ambas.

    Returns
    -------
    Un :class:`Resultado` con el veredicto y la traza de la comparación.
    """
    if respuesta is None or not respuesta.strip():
        return Resultado(Veredicto.SIN_RESPUESTA, None)

    try:
        with _limite_de_tiempo(SEGUNDOS_LIMITE):
            return _verificar_sin_limite(respuesta, clave, tipo)
    except _TiempoAgotado:
        return Resultado(
            Veredicto.NO_PARSEABLE,
            respuesta,
            detalle=f"La verificación excedió {SEGUNDOS_LIMITE}s",
        )


def _verificar_sin_limite(respuesta: str, clave: str, tipo: TipoRespuesta) -> Resultado:
    if tipo is TipoRespuesta.TEXTO:
        iguales = _normalizar_texto(respuesta) == _normalizar_texto(clave)
        return Resultado(
            Veredicto.CORRECTO if iguales else Veredicto.INCORRECTO,
            respuesta,
            forma_normalizada=_normalizar_texto(respuesta),
        )

    if tipo in (TipoRespuesta.CONJUNTO, TipoRespuesta.TUPLA):
        return _verificar_coleccion(respuesta, clave, tipo)

    try:
        expr_respuesta = _parsear(respuesta)
    except Exception as exc:
        return Resultado(Veredicto.NO_PARSEABLE, respuesta, detalle=str(exc)[:200])

    try:
        expr_clave = _parsear(clave)
    except Exception as exc:
        raise ValueError(f"La clave canónica {clave!r} no es parseable: {exc}") from exc

    iguales = _equivalentes(expr_respuesta, expr_clave)
    return Resultado(
        Veredicto.CORRECTO if iguales else Veredicto.INCORRECTO,
        respuesta,
        forma_normalizada=str(sympy.simplify(expr_respuesta)),
    )


def _verificar_coleccion(respuesta: str, clave: str, tipo: TipoRespuesta) -> Resultado:
    """Compara conjuntos o tuplas de valores elemento a elemento."""

    def partir(texto: str) -> list[str]:
        limpio = _limpiar(texto).strip("{}()[] ")
        return [parte.strip() for parte in limpio.split(",") if parte.strip()]

    partes_respuesta = partir(respuesta)
    partes_clave = partir(clave)

    if len(partes_respuesta) != len(partes_clave):
        return Resultado(
            Veredicto.INCORRECTO,
            respuesta,
            detalle=(
                f"Cantidad de elementos distinta: {len(partes_respuesta)} "
                f"contra {len(partes_clave)}"
            ),
        )

    try:
        exprs_respuesta = [_parsear(p) for p in partes_respuesta]
        exprs_clave = [_parsear(p) for p in partes_clave]
    except Exception as exc:
        return Resultado(Veredicto.NO_PARSEABLE, respuesta, detalle=str(exc)[:200])

    if tipo is TipoRespuesta.TUPLA:
        iguales = all(
            _equivalentes(a, b) for a, b in zip(exprs_respuesta, exprs_clave, strict=True)
        )
    else:
        pendientes = list(exprs_clave)
        iguales = True
        for expr in exprs_respuesta:
            for indice, candidato in enumerate(pendientes):
                if _equivalentes(expr, candidato):
                    pendientes.pop(indice)
                    break
            else:
                iguales = False
                break

    return Resultado(
        Veredicto.CORRECTO if iguales else Veredicto.INCORRECTO,
        respuesta,
        forma_normalizada=", ".join(str(e) for e in exprs_respuesta),
    )
