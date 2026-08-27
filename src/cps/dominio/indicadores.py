"""Indicadores del perfil de diseño de una instancia con partición de información.

Todo este módulo es función pura sobre números: no toca la base, no llama a la red
y no depende de FastAPI. Esa separación es deliberada, porque es la capa que tiene
que poder auditarse y replicarse de forma independiente del resto del sistema.

Notación
--------
Una instancia reparte dos datos privados, ``D = {a, b}``. Para cada subconjunto
``S ⊆ D`` se define la *función de competencia*

    v(S) = Pr[ solver(enunciado ∪ S) = respuesta_canónica ]

respecto de un **solver de referencia** declarado (modelo, versión, temperatura,
prompt). El par ``(D, v)`` es un juego cooperativo de dos jugadores, y sobre él se
construyen todos los indicadores de este módulo.

La estimación de cada ``v(S)`` es una proporción binomial sobre ``N`` ejecuciones
independientes; véase :func:`intervalo_wilson` y :func:`cota_superior_sin_exitos`.

Referencias internas
--------------------
Las definiciones y proposiciones citadas en los docstrings corresponden al
documento ``paper/cpp_framework.tex``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "Celda",
    "Competencia",
    "PerfilDiseno",
    "cota_superior_sin_exitos",
    "intervalo_wilson",
    "nivel_colaboratividad",
]

# Cuantil normal estándar al 97.5 %, para intervalos bilaterales al 95 %.
Z_975: Final[float] = 1.959963984540054

# Umbral de interdependencia por debajo del cual se considera que la partición
# dejó de estar operativa (definición de t_crit en el marco).
UMBRAL_INTERDEPENDENCIA: Final[float] = 0.5

# Tolerancia numérica para comparaciones de punto flotante en las validaciones.
_EPS: Final[float] = 1e-9


class Celda(StrEnum):
    """Las cuatro celdas de información sobre las que se estima ``v``.

    Son los cuatro subconjuntos de ``D = {a, b}``: sin ningún dato privado, con
    uno, con el otro, y con ambos.
    """

    VACIA = "vacia"
    """Sólo el enunciado público. Estima el desempeño por azar o por fuga."""

    SOLO_A = "solo_a"
    """Enunciado más el dato privado del participante A."""

    SOLO_B = "solo_b"
    """Enunciado más el dato privado del participante B."""

    AMBOS = "ambos"
    """Enunciado más ambos datos: la información completa."""


# ---------------------------------------------------------------------------
# Estimación de proporciones
# ---------------------------------------------------------------------------


def intervalo_wilson(exitos: int, ensayos: int, z: float = Z_975) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción binomial.

    Se prefiere al intervalo de Wald porque no colapsa a un punto cuando la
    proporción observada es 0 o 1, que es exactamente el caso que más importa
    acá: una celda individual de la que se espera que el solver nunca acierte.

    Parameters
    ----------
    exitos, ensayos:
        Conteos observados. ``0 <= exitos <= ensayos`` y ``ensayos > 0``.
    z:
        Cuantil normal. Por defecto, bilateral al 95 %.

    Returns
    -------
    Los extremos ``(inferior, superior)``, recortados a ``[0, 1]``.
    """
    if ensayos <= 0:
        raise ValueError("El número de ensayos debe ser positivo")
    if not 0 <= exitos <= ensayos:
        raise ValueError(f"exitos={exitos} fuera de rango para ensayos={ensayos}")

    n = float(ensayos)
    p = exitos / n
    denominador = 1.0 + z * z / n
    centro = (p + z * z / (2.0 * n)) / denominador
    margen = (z / denominador) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, centro - margen), min(1.0, centro + margen)


def cota_superior_sin_exitos(ensayos: int, confianza: float = 0.95) -> float:
    """Cota superior exacta para ``v`` cuando ninguna ejecución acierta.

    Si ``n`` ensayos independientes con probabilidad ``p`` no producen ningún
    éxito, entonces ``(1 - p)**n >= 1 - confianza`` en el borde, de donde la cota
    unilateral es ``1 - (1 - confianza)**(1/n)``. Es la versión exacta de la
    conocida "regla de tres" (``≈ 3/n`` al 95 %).

    Sirve para dimensionar cuántas ejecuciones hacen falta para *certificar* la
    insuficiencia individual de un dato: con 30 ensayos se acota v ≲ 0.095, y con
    60 ensayos v ≲ 0.049.
    """
    if ensayos <= 0:
        raise ValueError("El número de ensayos debe ser positivo")
    if not 0.0 < confianza < 1.0:
        raise ValueError("La confianza debe estar en (0, 1)")
    return 1.0 - (1.0 - confianza) ** (1.0 / ensayos)


# ---------------------------------------------------------------------------
# Función de competencia
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Competencia:
    """La función de competencia ``v`` estimada sobre las cuatro celdas.

    Es el único insumo de todos los indicadores de diseño: una vez medidas estas
    cuatro proporciones, ``IE_0``, ``IBC`` y la dificultad se derivan sin ningún
    experimento adicional.

    Attributes
    ----------
    vacia, solo_a, solo_b, ambos:
        Estimaciones de ``v(∅)``, ``v({a})``, ``v({b})`` y ``v(D)``.
    ensayos_por_celda:
        ``N`` usado en cada celda, necesario para propagar la incertidumbre.
    """

    vacia: float
    solo_a: float
    solo_b: float
    ambos: float
    ensayos_por_celda: int

    def __post_init__(self) -> None:
        for nombre in ("vacia", "solo_a", "solo_b", "ambos"):
            valor = getattr(self, nombre)
            if not 0.0 - _EPS <= valor <= 1.0 + _EPS:
                raise ValueError(f"v({nombre}) = {valor} fuera de [0, 1]")
        if self.ensayos_por_celda <= 0:
            raise ValueError("ensayos_por_celda debe ser positivo")

    # -- propiedades derivadas ------------------------------------------------

    @property
    def ganancia_alcanzable(self) -> float:
        """``Δ = v(D) - v(∅)``: cuánta competencia agrega la partición completa.

        Es el denominador de la normalización, y su cercanía a cero es la
        condición de degeneración de la instancia.
        """
        return self.ambos - self.vacia

    @property
    def es_degenerada(self) -> bool:
        """``True`` si la partición no agrega competencia sobre el enunciado solo.

        Una instancia degenerada no admite indicadores normalizados: o bien es
        imposible incluso con ambos datos, o bien el enunciado público ya filtra
        la respuesta.
        """
        return self.ganancia_alcanzable <= _EPS

    @property
    def viola_monotonia(self) -> bool:
        """``True`` si se viola ``v(∅) <= v({d_i}) <= v(D)``.

        El supuesto de monotonía informacional es normativo, no empírico: un
        resolutor ideal no empeora al recibir más información. Los modelos reales
        pueden violarlo por distracción. No se corrige silenciosamente: se marca,
        porque es un diagnóstico sobre la instancia o sobre el solver.
        """
        return not (
            self.vacia <= self.solo_a + _EPS
            and self.vacia <= self.solo_b + _EPS
            and self.solo_a <= self.ambos + _EPS
            and self.solo_b <= self.ambos + _EPS
        )

    # -- indicadores ----------------------------------------------------------

    def interdependencia(self) -> float:
        """``IE_0``: interdependencia epistémica de diseño (Definición 3.5).

            IE_0 = 1 - max_i [ v({d_i}) - v(∅) ] / Δ

        La normalización por ``Δ`` es lo que distingue esta formulación de la del
        marco de partida, que usaba ``1 - max_i v({d_i})`` sin normalizar. Sin
        normalizar, una instancia *imposible* (nadie la resuelve ni con ambos
        datos) alcanza el valor máximo del indicador sin ser colaborativa: el
        indicador confunde dificultad con interdependencia. Dividir por la
        ganancia alcanzable separa los dos constructos y deja la dificultad como
        indicador propio (:meth:`dificultad`).

        Returns
        -------
        Valor en ``[0, 1]``. Vale 1 cuando ningún dato aislado mejora sobre el
        enunciado solo, y 0 cuando alguno alcanza por sí mismo toda la ganancia.

        Raises
        ------
        ValueError
            Si la instancia es degenerada, en cuyo caso el indicador no está
            definido.
        """
        if self.es_degenerada:
            raise ValueError(
                "Instancia degenerada (Δ ≈ 0): la interdependencia normalizada "
                "no está definida. Revisar el enunciado o la dificultad."
            )
        mejor_individual = max(self.solo_a - self.vacia, self.solo_b - self.vacia)
        return _recortar(1.0 - mejor_individual / self.ganancia_alcanzable)

    def contribuciones_shapley(self) -> tuple[float, float]:
        """Valores de Shapley ``(φ_a, φ_b)`` del juego ``(D, v)``.

        Para dos jugadores,

            φ_a = ½[v({a}) - v(∅)] + ½[v(D) - v({b})]

        Cumple el axioma de eficiencia, ``φ_a + φ_b = Δ`` (Proposición 3.11).
        """
        phi_a = 0.5 * (self.solo_a - self.vacia) + 0.5 * (self.ambos - self.solo_b)
        phi_b = 0.5 * (self.solo_b - self.vacia) + 0.5 * (self.ambos - self.solo_a)
        return phi_a, phi_b

    def balance_carga(self) -> float:
        """``IBC``: balance de carga informativa (Definición 3.12).

            IBC = 1 - |φ_a - φ_b| / Δ = 1 - |v({a}) - v({b})| / Δ

        La segunda igualdad es la Proposición 3.11(ii), y es lo que vuelve
        práctico al indicador: la diferencia de valores de Shapley colapsa, para
        dos jugadores, a la diferencia de competencias individuales. El índice se
        calcula entonces con las mismas cuatro proporciones que ``IE_0``, sin
        experimento adicional y sin entropías condicionales, que era el punto
        débil de la formulación original.

        Un valor cercano a 1 indica que ambos datos aportan lo mismo; cercano a 0,
        que uno de los participantes es un validador pasivo de un problema que el
        otro ya resolvió.
        """
        if self.es_degenerada:
            raise ValueError(
                "Instancia degenerada (Δ ≈ 0): el balance de carga no está definido."
            )
        return _recortar(1.0 - abs(self.solo_a - self.solo_b) / self.ganancia_alcanzable)

    def dificultad(self) -> float:
        """``1 - v(D)``: cuán difícil es la instancia aun teniendo ambos datos.

        Se reporta por separado de :meth:`interdependencia` precisamente para no
        confundir los dos constructos.
        """
        return _recortar(1.0 - self.ambos)

    def error_estandar_balance(self) -> float:
        """Error estándar de ``IBC`` por método delta (Proposición 3.14).

        Con ``g(v) = (v_a - v_b) / (v_D - v_∅)`` y celdas independientes de
        tamaño ``N``,

            Var(ĝ) ≈ [v_a(1-v_a) + v_b(1-v_b)] / (N Δ²)
                   + (v_a - v_b)² [v_D(1-v_D) + v_∅(1-v_∅)] / (N Δ⁴)

        El término en ``Δ⁻⁴`` es la advertencia importante: la estimación se
        degrada rápido cuando la ganancia alcanzable es chica. Con ``Δ`` pequeño
        conviene usar bootstrap en lugar de esta aproximación normal.
        """
        if self.es_degenerada:
            raise ValueError("Instancia degenerada (Δ ≈ 0): el método delta no aplica.")

        n = float(self.ensayos_por_celda)
        delta = self.ganancia_alcanzable
        diferencia = self.solo_a - self.solo_b

        primer_termino = (
            _varianza_bernoulli(self.solo_a) + _varianza_bernoulli(self.solo_b)
        ) / (n * delta**2)
        segundo_termino = (
            diferencia**2
            * (_varianza_bernoulli(self.ambos) + _varianza_bernoulli(self.vacia))
        ) / (n * delta**4)
        return math.sqrt(primer_termino + segundo_termino)


def _varianza_bernoulli(p: float) -> float:
    return p * (1.0 - p)


def _recortar(valor: float, minimo: float = 0.0, maximo: float = 1.0) -> float:
    """Recorta a ``[minimo, maximo]``, absorbiendo error de punto flotante."""
    return max(minimo, min(maximo, valor))


# ---------------------------------------------------------------------------
# Perfil de diseño
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PerfilDiseno:
    """Perfil ``Φ`` de una instancia: los indicadores que no dependen del episodio.

    La distinción entre este perfil y el perfil de episodio no es organizativa
    sino conceptual. ``Φ`` depende sólo de la instancia y del solver de
    referencia, y por lo tanto es **idéntico bajo ambas modalidades** de
    resolución. Es la base común que permite comparar el diálogo agente-agente
    con el diálogo agente-estudiante: sin un perfil independiente de la
    modalidad, cualquier diferencia observada podría atribuirse a que se están
    comparando, en rigor, dos instancias distintas.
    """

    interdependencia: float
    balance_carga: float
    emergencia: float
    rondas_minimas: int
    dificultad: float
    ganancia_alcanzable: float
    monotonia_violada: bool

    @classmethod
    def desde_competencia(
        cls,
        competencia: Competencia,
        *,
        emergencia: float,
        rondas_minimas: int,
    ) -> PerfilDiseno:
        """Construye el perfil combinando la competencia medida con el DAG anotado.

        ``emergencia`` y ``rondas_minimas`` provienen de :mod:`cps.dominio.dag`,
        que los deriva de la estructura de la resolución canónica y no de una
        medición empírica.
        """
        return cls(
            interdependencia=competencia.interdependencia(),
            balance_carga=competencia.balance_carga(),
            emergencia=emergencia,
            rondas_minimas=rondas_minimas,
            dificultad=competencia.dificultad(),
            ganancia_alcanzable=competencia.ganancia_alcanzable,
            monotonia_violada=competencia.viola_monotonia,
        )

    def como_vector(self) -> tuple[float, ...]:
        """Representación vectorial, en orden estable, para el análisis posterior.

        El orden es parte del contrato: los análisis de correlación y de
        componentes principales dependen de que sea reproducible.
        """
        return (
            self.interdependencia,
            self.balance_carga,
            self.emergencia,
            float(self.rondas_minimas),
            self.dificultad,
        )

    def cumple_criterio_de_diseno(
        self, *, interdependencia_minima: float = 0.8, rondas_minimas_exigidas: int = 2
    ) -> bool:
        """Criterio prescriptivo para admitir una instancia al banco.

        Exige interdependencia alta y que la estructura de la solución obligue a
        por lo menos dos alternancias de lado: una instancia que se resuelve con
        un único intercambio de datos no es colaborativa en el sentido que
        interesa, es un problema común partido en dos.
        """
        return (
            self.interdependencia >= interdependencia_minima
            and self.rondas_minimas >= rondas_minimas_exigidas
            and not self.monotonia_violada
        )


def nivel_colaboratividad(interdependencia: float) -> str:
    """Etiqueta legible para una puntuación de interdependencia en ``[0, 1]``.

    Es presentación, no medición: los umbrales son convencionales y no deben
    usarse en el análisis, que trabaja siempre sobre el valor continuo.
    """
    if interdependencia >= 0.80:
        return "Altamente interdependiente"
    if interdependencia >= 0.60:
        return "Interdependiente"
    if interdependencia >= 0.40:
        return "Parcialmente interdependiente"
    return "Débilmente interdependiente"
