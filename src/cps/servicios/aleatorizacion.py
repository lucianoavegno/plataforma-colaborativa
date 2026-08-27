"""Asignación de condiciones experimentales de forma reproducible.

Dos requisitos que suelen estar en tensión:

* la asignación tiene que ser **impredecible** para quien participa, para que no
  pueda anticipar la condición;
* tiene que ser **reconstruible** después, para que el análisis pueda verificar
  que la asignación fue la declarada.

Se resuelve derivando la asignación por hash de una semilla fija junto con los
identificadores del episodio, en lugar de sortearla con un generador global. Así
no hay estado compartido, la asignación es determinista dada la semilla, y
reconstruirla no requiere haber guardado el orden en que se corrieron los
episodios.

Además, la asignación se **balancea** contra lo ya asignado para esa instancia:
un sorteo puramente independiente produce desbalances apreciables con los
tamaños de muestra de este estudio.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cps.modelos.entidades import CondicionDivulgacion, LadoAsignado, Modalidad

__all__ = ["Asignacion", "asignar_condicion", "sorteo_estable"]

# Mayor entero con signo que SQLite puede almacenar (2**63 - 1).
MAXIMO_ENTERO = (1 << 63) - 1


@dataclass(frozen=True, slots=True)
class Asignacion:
    """Condición y rol asignados a un episodio."""

    condicion: CondicionDivulgacion
    lado_humano: LadoAsignado | None
    semilla_efectiva: int


def sorteo_estable(*componentes: object, semilla: int) -> int:
    """Entero determinista derivado de la semilla y los componentes dados.

    Reemplaza a un generador con estado: la misma entrada produce siempre el
    mismo valor, sin importar en qué orden se hayan procesado otros episodios.
    """
    material = "|".join(str(c) for c in (semilla, *componentes))
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    # Se recorta a 63 bits para que entre en un entero con signo: el valor se
    # persiste con el episodio, y SQLite no admite enteros de 64 bits sin signo.
    return int.from_bytes(digest[:8], "big") & MAXIMO_ENTERO


def asignar_condicion(
    *,
    modalidad: Modalidad,
    instancia_id: int,
    cuenta_id: int,
    semilla: int,
    condiciones_previas: dict[str, int] | None = None,
    lados_previos: dict[str, int] | None = None,
) -> Asignacion:
    """Asigna condición de divulgación y, si corresponde, lado del humano.

    Parameters
    ----------
    condiciones_previas, lados_previos:
        Conteos de lo ya asignado para esta instancia y modalidad. Cuando hay
        desbalance, se asigna la celda menos poblada en lugar de sortear; con
        empate se recurre al sorteo estable. Es un balanceo por minimización,
        que mantiene las celdas parejas sin volver predecible la asignación
        cuando están equilibradas.
    semilla:
        Semilla del protocolo. Queda registrada en el episodio.
    """
    valor = sorteo_estable(modalidad, instancia_id, cuenta_id, semilla=semilla)

    condicion = _elegir_balanceado(
        opciones=[CondicionDivulgacion.LIBRE, CondicionDivulgacion.RESTRINGIDA],
        conteos=condiciones_previas or {},
        desempate=valor,
    )

    # El contrabalanceo de rol sólo tiene sentido cuando hay un humano: en
    # agente-agente los dos roles son artificiales, así que no hay confusión
    # entre modalidad y rol que corregir.
    lado: LadoAsignado | None = None
    if modalidad is Modalidad.AGENTE_ESTUDIANTE:
        lado = _elegir_balanceado(
            opciones=[LadoAsignado.A, LadoAsignado.B],
            conteos=lados_previos or {},
            desempate=valor >> 8,
        )

    return Asignacion(condicion=condicion, lado_humano=lado, semilla_efectiva=valor)


def _elegir_balanceado(*, opciones: list, conteos: dict[str, int], desempate: int):
    """Elige la opción menos usada; ante empate, decide el sorteo estable."""
    minimo = min(conteos.get(str(opcion), 0) for opcion in opciones)
    candidatas = [opcion for opcion in opciones if conteos.get(str(opcion), 0) == minimo]
    return candidatas[desempate % len(candidatas)]
