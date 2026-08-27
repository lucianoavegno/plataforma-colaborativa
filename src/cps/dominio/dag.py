"""Estructura de la resolución canónica como grafo dirigido acíclico.

La resolución de una instancia no se guarda sólo como prosa en LaTeX: se anota
además como un DAG de pasos deductivos, donde cada nodo declara de qué otros
pasos depende. Esa anotación es la que permite derivar dos cantidades que ninguna
medición sobre transcripts puede dar:

* la **emergencia epistémica** (``MEE``), o qué fracción del razonamiento sólo
  existe como producto de la deducción conjunta; y
* la **cota inferior de rondas** (``t_min``), o cuántos intercambios exige como
  mínimo la estructura de dependencias.

``t_min`` es lo que vuelve interpretable la eficiencia de un episodio: sin una
cota estructural, "resolvió en 7 turnos" no dice nada, porque no se sabe si el
piso era 2 o era 6.

Anotar el DAG es trabajo manual y no se puede automatizar sin perder el sentido
de la anotación. A cambio, es un artefacto reutilizable y auditable: dos personas
pueden anotar la misma resolución y comparar.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["ErrorDeEstructura", "EstructuraSolucion", "Lado", "Paso"]


class ErrorDeEstructura(ValueError):
    """El DAG anotado es inconsistente (ciclo, dependencia inexistente, etc.)."""


class Lado(StrEnum):
    """De qué información privada depende directamente un paso."""

    PUBLICO = "publico"
    """Derivable sólo del enunciado. No informa sobre la partición."""

    A = "a"
    """Requiere el dato privado de A."""

    B = "b"
    """Requiere el dato privado de B."""

    CONJUNTO = "conjunto"
    """Requiere ambos datos a la vez: es un paso emergente."""


@dataclass(frozen=True, slots=True)
class Paso:
    """Un nodo del DAG: una proposición o paso deductivo de la resolución.

    Attributes
    ----------
    id:
        Identificador estable dentro de la instancia. Aparece en la exportación,
        así que no debería cambiar una vez publicada la instancia.
    enunciado:
        Descripción breve del paso, en lenguaje natural o LaTeX.
    lado:
        Qué información privada requiere el paso *por sí mismo*, sin contar lo
        que herede de sus dependencias. La herencia la calcula
        :meth:`EstructuraSolucion.lado_efectivo`.
    depende_de:
        Identificadores de los pasos previos necesarios.
    """

    id: str
    enunciado: str
    lado: Lado
    depende_de: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EstructuraSolucion:
    """El DAG completo de una resolución canónica.

    Se valida en construcción: identificadores únicos, dependencias existentes y
    ausencia de ciclos. Un DAG mal anotado produciría indicadores silenciosamente
    equivocados, así que conviene que falle temprano y ruidosamente.
    """

    pasos: tuple[Paso, ...]
    paso_final: str
    _por_id: dict[str, Paso] = field(init=False, repr=False, compare=False)
    _cache_lado: dict[str, Lado] = field(init=False, repr=False, compare=False)
    _cache_ejecutor: dict[str, Lado] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        por_id: dict[str, Paso] = {}
        for paso in self.pasos:
            if paso.id in por_id:
                raise ErrorDeEstructura(f"Identificador de paso duplicado: {paso.id!r}")
            por_id[paso.id] = paso

        for paso in self.pasos:
            for dependencia in paso.depende_de:
                if dependencia not in por_id:
                    raise ErrorDeEstructura(
                        f"El paso {paso.id!r} depende de {dependencia!r}, que no existe"
                    )

        if self.paso_final not in por_id:
            raise ErrorDeEstructura(f"El paso final {self.paso_final!r} no existe")

        object.__setattr__(self, "_por_id", por_id)
        object.__setattr__(self, "_cache_lado", {})
        object.__setattr__(self, "_cache_ejecutor", {})
        self._verificar_aciclico()

    # -- validación -----------------------------------------------------------

    def _verificar_aciclico(self) -> None:
        """Detecta ciclos por ordenamiento topológico (algoritmo de Kahn)."""
        grado_entrada = {paso.id: len(paso.depende_de) for paso in self.pasos}
        dependientes: dict[str, list[str]] = {paso.id: [] for paso in self.pasos}
        for paso in self.pasos:
            for dependencia in paso.depende_de:
                dependientes[dependencia].append(paso.id)

        cola = deque(id_ for id_, grado in grado_entrada.items() if grado == 0)
        visitados = 0
        while cola:
            actual = cola.popleft()
            visitados += 1
            for siguiente in dependientes[actual]:
                grado_entrada[siguiente] -= 1
                if grado_entrada[siguiente] == 0:
                    cola.append(siguiente)

        if visitados != len(self.pasos):
            raise ErrorDeEstructura(
                "El grafo de la resolución tiene un ciclo: no es un DAG válido"
            )

    # -- clausuras ------------------------------------------------------------

    def lado_efectivo(self, id_paso: str) -> Lado:
        """Lado del paso una vez propagadas las dependencias.

        Un paso anotado como ``PUBLICO`` que depende de un paso ``A`` es, en los
        hechos, un paso que requiere el dato de A. Y un paso que hereda ``A`` por
        una rama y ``B`` por otra es ``CONJUNTO``, aunque él mismo no invoque
        ningún dato privado: esa es justamente la forma en que la emergencia
        aparece en la estructura.
        """
        if id_paso in self._cache_lado:
            return self._cache_lado[id_paso]

        paso = self._obtener(id_paso)
        lados = {paso.lado}
        for dependencia in paso.depende_de:
            lados.add(self.lado_efectivo(dependencia))

        lados.discard(Lado.PUBLICO)
        if not lados:
            resultado = Lado.PUBLICO
        elif Lado.CONJUNTO in lados or lados == {Lado.A, Lado.B}:
            resultado = Lado.CONJUNTO
        else:
            resultado = lados.pop()

        self._cache_lado[id_paso] = resultado
        return resultado

    def lado_ejecutor(self, id_paso: str) -> Lado:
        """Qué parte lleva a cabo el paso, que no es lo mismo que qué requiere.

        :meth:`lado_efectivo` acumula requisitos: una vez que un camino tocó los
        dos datos privados, todo lo que sigue queda marcado como ``CONJUNTO``.
        Esa es la noción correcta para las clausuras y la emergencia, porque
        describe qué hace falta para *alcanzar* el paso.

        Para contar intercambios hace falta la otra noción: quién ejecuta el
        paso. Un paso con lado declarado lo ejecuta esa parte, sin importar de
        qué venga; un paso público lo ejecuta quien haya producido sus insumos.
        Sin esta distinción, la saturación en ``CONJUNTO`` haría invisibles todas
        las alternancias posteriores a la primera confluencia, y ``t_min``
        quedaría sistemáticamente subestimado.
        """
        if id_paso in self._cache_ejecutor:
            return self._cache_ejecutor[id_paso]

        paso = self._obtener(id_paso)
        if paso.lado is not Lado.PUBLICO:
            resultado = paso.lado
        else:
            heredados = {self.lado_ejecutor(dep) for dep in paso.depende_de}
            heredados.discard(Lado.PUBLICO)
            if not heredados:
                resultado = Lado.PUBLICO
            elif Lado.CONJUNTO in heredados or heredados == {Lado.A, Lado.B}:
                resultado = Lado.CONJUNTO
            else:
                resultado = heredados.pop()

        self._cache_ejecutor[id_paso] = resultado
        return resultado

    def clausura(self, lados_disponibles: frozenset[Lado]) -> frozenset[str]:
        """Pasos derivables cuando se dispone de los datos privados indicados.

        Un paso es derivable si su lado efectivo está cubierto por lo disponible
        y todas sus dependencias también lo son.
        """
        derivables: set[str] = set()
        for _ in range(len(self.pasos)):
            crecio = False
            for paso in self.pasos:
                if paso.id in derivables:
                    continue
                if any(dep not in derivables for dep in paso.depende_de):
                    continue
                if self._cubierto(self.lado_efectivo(paso.id), lados_disponibles):
                    derivables.add(paso.id)
                    crecio = True
            if not crecio:
                break
        return frozenset(derivables)

    @staticmethod
    def _cubierto(lado: Lado, disponibles: frozenset[Lado]) -> bool:
        if lado is Lado.PUBLICO:
            return True
        if lado is Lado.CONJUNTO:
            return Lado.A in disponibles and Lado.B in disponibles
        return lado in disponibles

    # -- indicadores ----------------------------------------------------------

    def emergencia(self) -> float:
        """``MEE``: fracción de pasos que exigen la deducción conjunta.

            MEE = |V \\ (Cl({a}) ∪ Cl({b}))| / |V \\ Cl(∅)|

        El denominador excluye los pasos derivables del enunciado público, que no
        informan sobre la partición: si no se normalizara, una resolución con
        mucho preámbulo trivial daría emergencia artificialmente baja.

        Returns
        -------
        Valor en ``[0, 1]``. Vale 0 si la unión de lo que cada uno puede derivar
        por separado ya cubre toda la resolución, y 1 si ningún paso no trivial
        es alcanzable sin ambos datos.
        """
        publicos = self.clausura(frozenset())
        solo_a = self.clausura(frozenset({Lado.A}))
        solo_b = self.clausura(frozenset({Lado.B}))

        no_triviales = {paso.id for paso in self.pasos} - publicos
        if not no_triviales:
            return 0.0

        emergentes = no_triviales - (solo_a | solo_b)
        return len(emergentes) / len(no_triviales)

    def rondas_minimas(self) -> int:
        """``t_min``: cota inferior estructural sobre el número de intercambios.

        Se define como el máximo, sobre los caminos dirigidos del grafo, del
        número de alternancias de lado entre pasos consecutivos:

            t_min = max_π #{ j : lado(π_j) ≠ lado(π_{j+1}), ambos en {A, B} }

        La justificación es directa: si un paso que requiere el dato de A depende
        de un paso que requiere el dato de B, esa dependencia sólo puede
        satisfacerse si B le comunicó algo a A. Cada alternancia en la cadena de
        dependencias obliga por lo menos a una transmisión.

        Es una cota inferior, no una predicción: un episodio real puede usar más
        rondas, y de hecho casi siempre lo hace. Esa razón es exactamente la
        eficiencia del episodio.
        """
        memo: dict[str, int] = {}

        def alternancias_hasta(id_paso: str) -> int:
            """Máximo de alternancias en un camino que termina en ``id_paso``."""
            if id_paso in memo:
                return memo[id_paso]

            paso = self._obtener(id_paso)
            mi_lado = self.lado_ejecutor(id_paso)
            mejor = 0
            for dependencia in paso.depende_de:
                acumulado = alternancias_hasta(dependencia)
                lado_previo = self.lado_ejecutor(dependencia)
                if self._hay_alternancia(lado_previo, mi_lado):
                    acumulado += 1
                mejor = max(mejor, acumulado)

            memo[id_paso] = mejor
            return mejor

        return max(alternancias_hasta(paso.id) for paso in self.pasos)

    @staticmethod
    def _hay_alternancia(anterior: Lado, siguiente: Lado) -> bool:
        """Hay alternancia si el camino cruza de un lado privado al otro.

        Un paso ``CONJUNTO`` cuenta como cruce respecto de cualquier lado
        privado, porque para construirlo hubo que reunir ambas mitades.
        """
        privados = {Lado.A, Lado.B}
        if anterior in privados and siguiente in privados:
            return anterior is not siguiente
        if anterior in privados and siguiente is Lado.CONJUNTO:
            return True
        return anterior is Lado.CONJUNTO and siguiente in privados

    # -- utilidades -----------------------------------------------------------

    def _obtener(self, id_paso: str) -> Paso:
        try:
            return self._por_id[id_paso]
        except KeyError as exc:
            raise ErrorDeEstructura(f"No existe el paso {id_paso!r}") from exc

    def verificar_particion_genuina(self) -> list[str]:
        """Chequeos de diseño sobre la anotación, devueltos como advertencias.

        No lanza excepción: una instancia puede entrar al banco con advertencias
        y quedar marcada. La decisión de excluirla es del investigador, no del
        código.
        """
        advertencias: list[str] = []

        # La insuficiencia individual se decide por clausura y no por el lado
        # efectivo del paso final: preguntar si cada parte, por separado, puede
        # alcanzar la conclusión es exactamente la propiedad que define a la
        # partición como genuina.
        alcanzable_por_a = self.paso_final in self.clausura(frozenset({Lado.A}))
        alcanzable_por_b = self.paso_final in self.clausura(frozenset({Lado.B}))

        if alcanzable_por_a:
            advertencias.append(
                "Quien tiene el dato A alcanza la conclusión sin el dato B: la "
                "partición no es genuina."
            )
        if alcanzable_por_b:
            advertencias.append(
                "Quien tiene el dato B alcanza la conclusión sin el dato A: la "
                "partición no es genuina."
            )

        if self.rondas_minimas() < 2:
            advertencias.append(
                "t_min < 2: la instancia se resuelve con un único intercambio; es "
                "un problema común partido en dos, no un problema colaborativo."
            )

        if self.emergencia() == 0.0:
            advertencias.append(
                "MEE = 0: no hay ningún paso que exija la deducción conjunta."
            )

        declarados = {paso.lado for paso in self.pasos}
        if Lado.A not in declarados or Lado.B not in declarados:
            advertencias.append(
                "Alguno de los dos datos no se declara como requisito de ningún paso."
            )

        return advertencias
