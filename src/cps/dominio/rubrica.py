"""Rúbrica de calidad del proceso colaborativo: la matriz de doce celdas.

El dominio de competencia se representa como el cruce de cuatro procesos
individuales de resolución con tres competencias colaborativas, lo que da doce
celdas. Cada celda se puntúa en una escala ordinal de cuatro niveles, y el
índice de calidad (``CQI``) es su promedio normalizado.

La distinción entre esta rúbrica y el perfil de diseño es la que separa lo
*descriptivo* de lo *prescriptivo*:

* el perfil de diseño describe qué exige la instancia, y no cambia entre
  episodios;
* esta rúbrica describe qué ocurrió en un episodio concreto, y varía entre
  réplicas de la misma instancia.

Confundirlas es el error formal que tenía el índice compuesto del marco de
partida, que sumaba un término prescriptivo constante a un término observado y
por lo tanto no podía funcionar como medida de rendimiento por episodio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Final

__all__ = [
    "CELDAS",
    "CODIGO_A_CELDA",
    "Celda",
    "CompetenciaColaborativa",
    "NivelCelda",
    "ProcesoIndividual",
    "VectorCalidad",
]


class ProcesoIndividual(StrEnum):
    """Los cuatro procesos individuales de resolución de problemas."""

    EXPLORAR = "explorar_comprender"
    REPRESENTAR = "representar_formular"
    PLANIFICAR = "planificar_ejecutar"
    MONITOREAR = "monitorear_reflexionar"


class CompetenciaColaborativa(StrEnum):
    """Las tres competencias colaborativas que se cruzan con los procesos."""

    COMPRENSION = "comprension_compartida"
    ACCION = "accion_apropiada"
    ORGANIZACION = "organizacion_equipo"


class NivelCelda(IntEnum):
    """Escala ordinal de una celda.

    Es ordinal y no de intervalo: la distancia entre FUNCIONAL y EMERGENTE no es
    necesariamente igual a la que hay entre AUSENTE y SUPERFICIAL. Por eso el
    acuerdo entre codificadores se mide con un coeficiente ordinal y no con una
    correlación de Pearson.
    """

    AUSENTE = 0
    """No hay evidencia de la conducta en el transcript."""

    SUPERFICIAL = 1
    """Aparece de forma nominal, sin consecuencia sobre la resolución."""

    FUNCIONAL = 2
    """Aparece y contribuye efectivamente a avanzar."""

    EMERGENTE = 3
    """Produce entendimiento conjunto que ninguna parte traía."""


@dataclass(frozen=True, slots=True, order=True)
class Celda:
    """Una celda de la matriz: un proceso cruzado con una competencia."""

    proceso: ProcesoIndividual
    competencia: CompetenciaColaborativa

    @property
    def codigo(self) -> str:
        """Clave estable y corta, usada en la exportación y en el prompt del juez."""
        siglas_proceso = {
            ProcesoIndividual.EXPLORAR: "EX",
            ProcesoIndividual.REPRESENTAR: "RE",
            ProcesoIndividual.PLANIFICAR: "PL",
            ProcesoIndividual.MONITOREAR: "MO",
        }
        siglas_competencia = {
            CompetenciaColaborativa.COMPRENSION: "CO",
            CompetenciaColaborativa.ACCION: "AC",
            CompetenciaColaborativa.ORGANIZACION: "OR",
        }
        return f"{siglas_proceso[self.proceso]}-{siglas_competencia[self.competencia]}"


CELDAS: Final[tuple[Celda, ...]] = tuple(
    Celda(proceso, competencia)
    for proceso in ProcesoIndividual
    for competencia in CompetenciaColaborativa
)
"""Las doce celdas, en orden estable. El orden es parte del contrato de datos."""

CODIGO_A_CELDA: Final[dict[str, Celda]] = {celda.codigo: celda for celda in CELDAS}

PUNTAJE_MAXIMO: Final[int] = len(CELDAS) * max(NivelCelda)  # 12 * 3 = 36


DESCRIPCIONES: Final[dict[str, str]] = {
    "EX-CO": "Descubrir qué sabe la otra parte sobre el problema.",
    "EX-AC": "Descubrir las capacidades y el rol de la otra parte al explorar.",
    "EX-OR": "Acordar cómo se va a explorar el problema entre ambos.",
    "RE-CO": "Construir una representación compartida del problema.",
    "RE-AC": "Describir y negociar qué hay que hacer para representarlo.",
    "RE-OR": "Acordar roles y turnos al formular el problema.",
    "PL-CO": "Comunicar el plan y mantener la comprensión mientras se ejecuta.",
    "PL-AC": "Ejecutar la parte propia del plan de forma coordinada.",
    "PL-OR": "Cumplir las reglas de interacción acordadas al ejecutar.",
    "MO-CO": "Vigilar y reparar la comprensión compartida.",
    "MO-AC": "Vigilar los resultados y ajustar la acción conjunta.",
    "MO-OR": "Vigilar la organización del trabajo y corregirla.",
}


@dataclass(frozen=True, slots=True)
class VectorCalidad:
    """Una codificación completa de las doce celdas para un episodio.

    Es inmutable a propósito: una codificación es un dato observado y no debería
    poder modificarse tras registrarse. Corregir una codificación se hace
    creando otra, no mutando la anterior, para que el historial quede.
    """

    puntajes: dict[str, NivelCelda]

    def __post_init__(self) -> None:
        faltantes = set(CODIGO_A_CELDA) - set(self.puntajes)
        if faltantes:
            raise ValueError(f"Faltan celdas en la codificación: {sorted(faltantes)}")
        sobrantes = set(self.puntajes) - set(CODIGO_A_CELDA)
        if sobrantes:
            raise ValueError(f"Celdas desconocidas en la codificación: {sorted(sobrantes)}")

    @classmethod
    def desde_dict(cls, datos: dict[str, int]) -> VectorCalidad:
        """Construye el vector desde enteros crudos, validando el rango."""
        convertidos: dict[str, NivelCelda] = {}
        for codigo, valor in datos.items():
            try:
                convertidos[codigo] = NivelCelda(valor)
            except ValueError as exc:
                raise ValueError(
                    f"Puntaje inválido para {codigo!r}: {valor}. "
                    f"Debe estar en {[n.value for n in NivelCelda]}."
                ) from exc
        return cls(convertidos)

    def indice_calidad(self) -> float:
        """``CQI``: promedio normalizado de las doce celdas, en ``[0, 1]``."""
        return sum(self.puntajes.values()) / PUNTAJE_MAXIMO

    def celdas_activas(self) -> int:
        """Cuántas celdas superan el nivel nominal.

        Se cuenta a partir de FUNCIONAL: una celda que aparece de forma
        superficial no es evidencia de que la competencia se haya ejercido.
        """
        return sum(1 for nivel in self.puntajes.values() if nivel >= NivelCelda.FUNCIONAL)

    def celdas_emergentes(self) -> int:
        """Cuántas celdas alcanzan el nivel de entendimiento conjunto nuevo."""
        return sum(1 for nivel in self.puntajes.values() if nivel == NivelCelda.EMERGENTE)

    def como_vector(self) -> tuple[int, ...]:
        """Vector de doce enteros en el orden estable de :data:`CELDAS`."""
        return tuple(int(self.puntajes[celda.codigo]) for celda in CELDAS)

    def perfil_por_competencia(self) -> dict[str, float]:
        """Promedio por competencia colaborativa, en ``[0, 1]``.

        Útil para diagnosticar en qué dimensión difieren dos modalidades: un
        ``CQI`` global igual puede esconder perfiles muy distintos.
        """
        resultado: dict[str, float] = {}
        for competencia in CompetenciaColaborativa:
            celdas = [c for c in CELDAS if c.competencia is competencia]
            total = sum(self.puntajes[c.codigo] for c in celdas)
            resultado[competencia.value] = total / (len(celdas) * max(NivelCelda))
        return resultado

    def perfil_por_proceso(self) -> dict[str, float]:
        """Promedio por proceso individual de resolución, en ``[0, 1]``."""
        resultado: dict[str, float] = {}
        for proceso in ProcesoIndividual:
            celdas = [c for c in CELDAS if c.proceso is proceso]
            total = sum(self.puntajes[c.codigo] for c in celdas)
            resultado[proceso.value] = total / (len(celdas) * max(NivelCelda))
        return resultado


def acuerdo_ordinal(
    codificacion_a: list[int], codificacion_b: list[int], niveles: int = 4
) -> float:
    """Alfa de Krippendorff para dos codificadores en escala ordinal.

    Se implementa acá, y no se toma de una biblioteca, porque el coeficiente es
    el que sostiene la validez de toda la codificación automática: conviene que
    esté a la vista y cubierto por tests.

    La forma general es ``α = 1 - D_o / D_e``, con ``D_o`` el desacuerdo
    observado y ``D_e`` el esperado por azar, ambos calculados con la métrica de
    diferencia ordinal.

    Parameters
    ----------
    codificacion_a, codificacion_b:
        Puntajes emparejados de dos codificadores sobre las mismas unidades.
    niveles:
        Cantidad de niveles de la escala (4 para :class:`NivelCelda`).

    Returns
    -------
    ``α`` en ``(-inf, 1]``. Por convención se usan 0.80 como umbral para
    conclusiones firmes y 0.667 como piso para conclusiones tentativas.
    """
    if len(codificacion_a) != len(codificacion_b):
        raise ValueError("Las codificaciones deben tener la misma longitud")
    if not codificacion_a:
        raise ValueError("Se necesita al menos una unidad codificada")

    unidades = len(codificacion_a)
    valores = codificacion_a + codificacion_b

    # Frecuencias marginales sobre el total de valores asignados.
    frecuencia = [0] * niveles
    for valor in valores:
        if not 0 <= valor < niveles:
            raise ValueError(f"Valor {valor} fuera de la escala de {niveles} niveles")
        frecuencia[valor] += 1

    def distancia_ordinal(i: int, j: int) -> float:
        """Métrica ordinal: penaliza según las frecuencias acumuladas entre i y j."""
        if i == j:
            return 0.0
        bajo, alto = min(i, j), max(i, j)
        acumulado = sum(frecuencia[bajo : alto + 1])
        correccion = (frecuencia[bajo] + frecuencia[alto]) / 2.0
        return (acumulado - correccion) ** 2

    desacuerdo_observado = (
        sum(distancia_ordinal(a, b) for a, b in zip(codificacion_a, codificacion_b, strict=True))
        / unidades
    )

    total = len(valores)
    desacuerdo_esperado = sum(
        frecuencia[i] * frecuencia[j] * distancia_ordinal(i, j)
        for i in range(niveles)
        for j in range(niveles)
    ) / (total * (total - 1))

    if desacuerdo_esperado == 0.0:
        # Sin variabilidad marginal no hay azar contra el cual comparar: si además
        # no hubo desacuerdo, el acuerdo es perfecto por definición.
        return 1.0 if desacuerdo_observado == 0.0 else 0.0

    return 1.0 - desacuerdo_observado / desacuerdo_esperado
