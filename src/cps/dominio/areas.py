"""Áreas de matemática que cubre el banco de instancias.

Se mantiene como tabla explícita y no como texto libre para que la
estratificación por área sea posible sin normalizar cadenas a posteriori.
"""

from __future__ import annotations

from typing import Final

AREAS: Final[dict[str, str]] = {
    "algebra_lineal": "Álgebra Lineal",
    "intro_algebra": "Introducción al Álgebra",
    "intro_calculo": "Introducción al Cálculo",
    "calculo_dif_int": "Cálculo Diferencial e Integral",
    "calculo_varias_variables": "Cálculo en Varias Variables",
    "edo": "Ecuaciones Diferenciales Ordinarias",
}


def es_area_valida(clave: str) -> bool:
    return clave in AREAS


def nombre_area(clave: str) -> str:
    """Nombre legible. Devuelve la clave si no está registrada, para no perder
    información al mostrar datos de una versión anterior del banco."""
    return AREAS.get(clave, clave)
