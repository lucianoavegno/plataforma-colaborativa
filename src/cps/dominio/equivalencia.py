"""Comparación entre modalidades: divergencia, equivalencia y equiparación.

Una misma instancia puede resolverse con dos agentes artificiales dialogando
entre sí, o con un agente y un estudiante. Este módulo implementa las
herramientas para comparar ambas modalidades sin cometer el error inferencial
más común en este tipo de comparación.

Ese error consiste en concluir que dos condiciones son equivalentes porque una
prueba no encontró diferencia significativa. No lo son: un estudio con poca
potencia produce ese resultado *sistemáticamente*, con lo cual la ausencia de
evidencia se confunde con evidencia de ausencia. Afirmar equivalencia exige
invertir la carga de la prueba y declarar de antemano cuánta diferencia se
considera despreciable. Eso es lo que hace :func:`prueba_equivalencia`.

Todo el módulo trabaja con estadísticos resumidos —medias, desvíos, tamaños— y
no con las muestras completas, para que pueda usarse tanto sobre datos en vivo
como sobre resultados ya agregados.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "Divergencia",
    "Modalidad",
    "Muestra",
    "ResultadoEquivalencia",
    "descomponer_divergencia",
    "diferencia_estandarizada",
    "episodios_para_equivalencia",
    "prueba_equivalencia",
    "resolucion_del_ordenamiento",
]

Z_95_UNILATERAL: Final[float] = 1.6448536269514722
Z_90: Final[float] = 1.2815515655446004


class Modalidad(StrEnum):
    """Las dos modalidades de resolución que el estudio compara.

    Se nombran de forma simétrica a propósito: ninguna es el criterio de la otra.
    El objeto de estudio es el mapa que las vincula, no la aproximación de una
    por la otra.
    """

    AGENTE_AGENTE = "agente_agente"
    """Dos agentes artificiales, cada uno con un dato privado."""

    AGENTE_ESTUDIANTE = "agente_estudiante"
    """Un agente artificial y un estudiante, cada uno con un dato privado."""


@dataclass(frozen=True, slots=True)
class Muestra:
    """Estadísticos resumidos de un componente bajo una modalidad."""

    media: float
    desvio: float
    n: int

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError("Se necesitan al menos 2 observaciones")
        if self.desvio < 0:
            raise ValueError("El desvío no puede ser negativo")

    @classmethod
    def desde_valores(cls, valores: Sequence[float]) -> Muestra:
        """Calcula media y desvío muestral (con corrección de Bessel)."""
        n = len(valores)
        if n < 2:
            raise ValueError("Se necesitan al menos 2 observaciones")
        media = sum(valores) / n
        varianza = sum((v - media) ** 2 for v in valores) / (n - 1)
        return cls(media=media, desvio=math.sqrt(varianza), n=n)


def desvio_agrupado(a: Muestra, b: Muestra) -> float:
    """Desvío agrupado de dos muestras independientes.

    Es el denominador de la diferencia estandarizada. Se agrupa ponderando por
    grados de libertad, que es lo correcto cuando los tamaños difieren.
    """
    gl = a.n + b.n - 2
    if gl <= 0:
        raise ValueError("Grados de libertad insuficientes")
    suma = (a.n - 1) * a.desvio**2 + (b.n - 1) * b.desvio**2
    return math.sqrt(suma / gl)


def diferencia_estandarizada(a: Muestra, b: Muestra, *, escala: float | None = None) -> float:
    """Diferencia de medias en unidades de desvío estándar.

    Parameters
    ----------
    a, b:
        Muestras a comparar. El signo del resultado es ``media(a) - media(b)``.
    escala:
        Desvío contra el cual estandarizar. Si se omite, se usa el agrupado de
        las dos muestras.

        En el estudio conviene pasar el desvío agrupado sobre **todo el banco**,
        no el de la instancia. Estandarizar dentro de cada instancia haría que
        una instancia con poca varianza interna produjera divergencias
        artificialmente enormes, y las divergencias dejarían de ser comparables
        entre instancias, que es justamente para lo que se las quiere.
    """
    denominador = escala if escala is not None else desvio_agrupado(a, b)
    if denominador <= 0:
        raise ValueError("La escala de estandarización debe ser positiva")
    return (a.media - b.media) / denominador


@dataclass(frozen=True, slots=True)
class ResultadoEquivalencia:
    """Salida de una prueba de equivalencia sobre un componente."""

    diferencia: float
    """Diferencia estandarizada observada."""

    margen: float
    """Margen de equivalencia declarado de antemano."""

    intervalo: tuple[float, float]
    """Intervalo de confianza al ``1 - 2α`` para la diferencia."""

    equivalentes: bool
    """El intervalo está contenido en ``[-margen, margen]``."""

    potencia_insuficiente: bool
    """El intervalo excede el margen por ancho, no por desplazamiento.

    Distingue "son distintas" de "no alcanzan los datos para decidir", que es la
    diferencia que la prueba está para hacer visible.
    """

    @property
    def conclusion(self) -> str:
        if self.equivalentes:
            return f"Equivalentes dentro de ±{self.margen}"
        if self.potencia_insuficiente:
            return "Indeterminado: el intervalo es más ancho que el margen"
        return f"Diferentes: la divergencia excede ±{self.margen}"


def prueba_equivalencia(
    a: Muestra,
    b: Muestra,
    *,
    margen: float,
    alfa: float = 0.05,
    escala: float | None = None,
) -> ResultadoEquivalencia:
    """Dos pruebas unilaterales (TOST) para declarar equivalencia.

    Se declara equivalencia cuando el intervalo de confianza al ``1 - 2α`` para
    la diferencia estandarizada queda íntegramente dentro de ``[-margen, margen]``;
    equivalentemente, cuando se rechazan las dos hipótesis unilaterales
    ``H01: d <= -margen`` y ``H02: d >= margen``.

    El margen no es un detalle técnico: es la declaración sustantiva de cuánta
    diferencia se considera irrelevante, y debe fijarse antes de ver los datos.
    """
    if margen <= 0:
        raise ValueError("El margen de equivalencia debe ser positivo")
    if not 0 < alfa < 0.5:
        raise ValueError("alfa debe estar en (0, 0.5)")

    escala_efectiva = escala if escala is not None else desvio_agrupado(a, b)
    if escala_efectiva <= 0:
        raise ValueError("La escala de estandarización debe ser positiva")

    diferencia = diferencia_estandarizada(a, b, escala=escala_efectiva)

    # Error estándar de la diferencia, expresado en la misma escala estandarizada.
    error_bruto = math.sqrt(a.desvio**2 / a.n + b.desvio**2 / b.n)
    error = error_bruto / escala_efectiva

    z = _cuantil_normal(1.0 - alfa)
    inferior = diferencia - z * error
    superior = diferencia + z * error

    equivalentes = inferior >= -margen and superior <= margen
    ancho_excesivo = (superior - inferior) > 2 * margen

    return ResultadoEquivalencia(
        diferencia=diferencia,
        margen=margen,
        intervalo=(inferior, superior),
        equivalentes=equivalentes,
        potencia_insuficiente=not equivalentes and ancho_excesivo,
    )


def episodios_para_equivalencia(
    margen: float, *, alfa: float = 0.05, potencia: float = 0.80
) -> int:
    """Episodios por modalidad necesarios para declarar equivalencia.

    Para dos grupos independientes de igual tamaño y divergencia verdadera nula,

        n ≈ 2 (z_{1-α} + z_{1-β/2})² / margen²

    Los números que salen de acá son grandes y esa es información de diseño, no
    un inconveniente: con margen 0.5 hacen falta unos 69 episodios por modalidad
    y por instancia, lo cual determina que la equivalencia a nivel de instancia
    individual sólo pueda sostenerse sobre un subconjunto reducido del banco.
    """
    if margen <= 0:
        raise ValueError("El margen debe ser positivo")
    if not 0 < potencia < 1:
        raise ValueError("La potencia debe estar en (0, 1)")

    z_alfa = _cuantil_normal(1.0 - alfa)
    z_beta = _cuantil_normal(1.0 - (1.0 - potencia) / 2.0)
    return math.ceil(2.0 * (z_alfa + z_beta) ** 2 / margen**2)


def resolucion_del_ordenamiento(margen: float, dispersion_entre_instancias: float) -> float:
    """Cuántos estratos de instancias son distinguibles con un margen dado.

    Si toda instancia tiene divergencia acotada por ``margen``, el orden entre
    dos instancias sólo se preserva cuando su separación supera ``2 · margen``
    desvíos. Con una dispersión entre instancias ``s``, el número de estratos
    distinguibles es del orden de ``s / (2 · margen)``.

    El resultado suele ser incómodo y conviene tenerlo a la vista antes de
    interpretar rankings: con dispersión 1.5 y margen 0.5 da 1.5, es decir que el
    procedimiento separa dos grupos y no produce un ordenamiento fino.
    """
    if margen <= 0:
        raise ValueError("El margen debe ser positivo")
    if dispersion_entre_instancias < 0:
        raise ValueError("La dispersión no puede ser negativa")
    return dispersion_entre_instancias / (2.0 * margen)


@dataclass(frozen=True, slots=True)
class Divergencia:
    """Descomposición de la divergencia esperada entre modalidades.

    Los tres términos suman la divergencia cuadrática esperada y admiten
    remedios distintos, que es la razón de separarlos:

    * ``sesgo_sistematico``: una modalidad es uniformemente más colaborativa que
      la otra. Es corregible por desplazamiento y no invalida el uso comparativo.
    * ``distorsion_escala``: con pendiente menor que 1, la modalidad artificial
      discrimina entre instancias menos que la humana. Degrada el ordenamiento
      sin desplazarlo.
    * ``idiosincratico``: la parte que depende de la instancia particular y no de
      ninguna transformación global. Es la única irreducible.
    """

    ordenada: float
    pendiente: float
    sesgo_sistematico: float
    distorsion_escala: float
    idiosincratico: float

    @property
    def total(self) -> float:
        return self.sesgo_sistematico + self.distorsion_escala + self.idiosincratico

    @property
    def proporcion_irreducible(self) -> float:
        """Fracción de la divergencia que ninguna transformación afín corrige."""
        if self.total <= 0:
            return 0.0
        return self.idiosincratico / self.total

    @property
    def preserva_orden(self) -> bool:
        """Una pendiente positiva basta para que el ordenamiento se conserve."""
        return self.pendiente > 0


def descomponer_divergencia(
    medias_agente_agente: Sequence[float],
    medias_agente_estudiante: Sequence[float],
) -> Divergencia:
    """Ajusta la equiparación lineal entre modalidades y descompone el error.

    Se ajusta por mínimos cuadrados ``y = a + b·x + e``, con ``x`` las medias por
    instancia bajo agente-estudiante e ``y`` bajo agente-agente, y se reparte

        E[(y - x)²] = (a + (b-1)E[x])² + (b-1)² Var(x) + Var(e)

    Parameters
    ----------
    medias_agente_agente, medias_agente_estudiante:
        Medias por instancia, emparejadas y en el mismo orden. La unidad de
        análisis es la instancia, no el episodio.
    """
    x = list(medias_agente_estudiante)
    y = list(medias_agente_agente)
    if len(x) != len(y):
        raise ValueError("Las series deben tener la misma longitud")
    if len(x) < 3:
        raise ValueError("Se necesitan al menos 3 instancias para la equiparación")

    n = len(x)
    media_x = sum(x) / n
    media_y = sum(y) / n

    varianza_x = sum((xi - media_x) ** 2 for xi in x) / n
    if varianza_x <= 0:
        raise ValueError(
            "Las medias bajo agente-estudiante no tienen dispersión: la "
            "equiparación no está identificada."
        )

    covarianza = sum((xi - media_x) * (yi - media_y) for xi, yi in zip(x, y, strict=True)) / n
    pendiente = covarianza / varianza_x
    ordenada = media_y - pendiente * media_x

    residuos = [yi - (ordenada + pendiente * xi) for xi, yi in zip(x, y, strict=True)]
    varianza_residual = sum(r**2 for r in residuos) / n

    return Divergencia(
        ordenada=ordenada,
        pendiente=pendiente,
        sesgo_sistematico=(ordenada + (pendiente - 1.0) * media_x) ** 2,
        distorsion_escala=(pendiente - 1.0) ** 2 * varianza_x,
        idiosincratico=varianza_residual,
    )


def correlacion_de_rangos(a: Sequence[float], b: Sequence[float]) -> float:
    """Coeficiente de Spearman entre dos series emparejadas.

    Es el estadístico de la compatibilidad relativa: mide si las instancias se
    ordenan igual bajo ambas modalidades, sin exigir que los niveles coincidan.
    """
    if len(a) != len(b):
        raise ValueError("Las series deben tener la misma longitud")
    if len(a) < 3:
        raise ValueError("Se necesitan al menos 3 pares")

    rangos_a = _rangos(a)
    rangos_b = _rangos(b)
    n = len(a)

    media_a = sum(rangos_a) / n
    media_b = sum(rangos_b) / n
    numerador = sum(
        (ra - media_a) * (rb - media_b) for ra, rb in zip(rangos_a, rangos_b, strict=True)
    )
    denominador = math.sqrt(
        sum((ra - media_a) ** 2 for ra in rangos_a)
        * sum((rb - media_b) ** 2 for rb in rangos_b)
    )
    if denominador == 0:
        return 0.0
    return numerador / denominador


def corregir_por_atenuacion(
    correlacion: float, confiabilidad_a: float, confiabilidad_b: float
) -> float:
    """Desatenúa una correlación entre dos medidas con error.

    Cuando ambos términos se miden con error, la correlación observada subestima
    la verdadera. La corrección clásica divide por la raíz del producto de las
    confiabilidades. Se reportan siempre las dos cifras, observada y corregida:
    la corregida sin la observada es fácil de inflar.
    """
    for nombre, valor in (("a", confiabilidad_a), ("b", confiabilidad_b)):
        if not 0 < valor <= 1:
            raise ValueError(f"La confiabilidad {nombre} debe estar en (0, 1]")
    return correlacion / math.sqrt(confiabilidad_a * confiabilidad_b)


def confiabilidad_spearman_brown(icc: float, episodios: int) -> float:
    """Confiabilidad de una media de ``k`` episodios por instancia.

        ρ_k = k · ICC / [1 + (k - 1) · ICC]

    Sirve para decidir cuántos episodios por instancia hacen falta antes de
    correlacionar medias: con ICC de 0.30 y 8 episodios se llega a 0.77, que
    alcanza para correlacionar pero no para interpretar valores individuales.
    """
    if not 0 <= icc <= 1:
        raise ValueError("El ICC debe estar en [0, 1]")
    if episodios < 1:
        raise ValueError("Se necesita al menos un episodio")
    if icc == 0:
        return 0.0
    return episodios * icc / (1.0 + (episodios - 1) * icc)


def _rangos(valores: Sequence[float]) -> list[float]:
    """Rangos con promedio en los empates."""
    indexados = sorted(range(len(valores)), key=lambda i: valores[i])
    rangos = [0.0] * len(valores)
    i = 0
    while i < len(indexados):
        j = i
        while j + 1 < len(indexados) and valores[indexados[j + 1]] == valores[indexados[i]]:
            j += 1
        rango_promedio = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rangos[indexados[k]] = rango_promedio
        i = j + 1
    return rangos


def _cuantil_normal(p: float) -> float:
    """Cuantil de la normal estándar por bisección sobre la función de error.

    Se implementa acá para no arrastrar scipy como dependencia del núcleo: el
    paquete de análisis puede usarlo, pero el dominio no debería necesitarlo.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p debe estar en (0, 1)")
    bajo, alto = -10.0, 10.0
    for _ in range(200):
        medio = (bajo + alto) / 2.0
        if 0.5 * (1.0 + math.erf(medio / math.sqrt(2.0))) < p:
            bajo = medio
        else:
            alto = medio
    return (bajo + alto) / 2.0
