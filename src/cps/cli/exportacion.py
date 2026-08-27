"""Exportación de episodios para análisis externo."""

from __future__ import annotations

import json
from pathlib import Path

from cps.db import sesion_de_trabajo


def exportar(
    *, salida: Path, incluir_simulados: bool = False, incluir_transcripts: bool = True
) -> int:
    """Vuelca los episodios a JSON por líneas, seudonimizados.

    El formato es una línea por episodio para que el archivo se pueda procesar
    en flujo y para que agregar campos no rompa a quien ya lo lee.
    """
    from cps.api.rutas.investigacion import _filas_episodios

    salida.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with sesion_de_trabajo() as sesion, salida.open("w", encoding="utf-8") as archivo:
        for fila in _filas_episodios(
            sesion,
            incluir_simulados=incluir_simulados,
            incluir_transcripts=incluir_transcripts,
        ):
            archivo.write(json.dumps(fila, ensure_ascii=False) + "\n")
            total += 1

    print(f"Se exportaron {total} episodio(s) a {salida}")
    if not incluir_simulados:
        print("Los episodios simulados quedaron excluidos (--incluir-simulados para incluirlos).")
    return 0
