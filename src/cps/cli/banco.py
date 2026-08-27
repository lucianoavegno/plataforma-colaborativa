"""Validación y publicación del banco de instancias."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from cps.db import sesion_de_trabajo
from cps.dominio.areas import nombre_area
from cps.modelos.entidades import Instancia
from cps.servicios.banco import (
    DefinicionInstancia,
    ErrorDeBanco,
    cargar_directorio,
    serializar_estructura,
)


def validar(directorio: Path) -> int:
    """Valida los archivos sin escribir nada.

    Se ejecuta antes de sembrar y en integración continua: un banco que no
    valida no debería llegar nunca a la base.
    """
    try:
        definiciones = cargar_directorio(directorio)
    except ErrorDeBanco as exc:
        print(f"✗ {exc}")
        return 1

    print(f"Se leyeron {len(definiciones)} instancias de {directorio}\n")

    con_advertencias = 0
    for definicion in sorted(definiciones, key=lambda d: (d.area, d.codigo)):
        advertencias = definicion.advertencias()
        marca = "!" if advertencias else "·"
        print(
            f" {marca} [{definicion.area}] {definicion.codigo}  "
            f"t_min={definicion.estructura.rondas_minimas()}  "
            f"MEE={definicion.estructura.emergencia():.2f}"
        )
        if advertencias:
            con_advertencias += 1
            for advertencia in advertencias:
                print(f"     ↳ {advertencia}")

    print()
    if con_advertencias:
        print(
            f"{con_advertencias} instancia(s) con advertencias de diseño. "
            "Revisalas antes de incluirlas en la recolección."
        )
    else:
        print("Ninguna instancia presenta advertencias de diseño.")

    _resumen_por_area(definiciones)
    return 0


def _resumen_por_area(definiciones: list[DefinicionInstancia]) -> None:
    por_area: dict[str, int] = {}
    for definicion in definiciones:
        por_area[definicion.area] = por_area.get(definicion.area, 0) + 1
    print("\nCobertura por área:")
    for area, cantidad in sorted(por_area.items()):
        print(f"  {nombre_area(area):38} {cantidad}")


def sembrar(directorio: Path, *, forzar: bool = False) -> int:
    """Publica el banco en la base, versionando por contenido.

    Una instancia cuyo contenido no cambió se deja intacta: no se toca la fila ni
    se invalidan sus mediciones. Si cambió, se publica una versión nueva y la
    anterior se desactiva, de modo que los episodios ya registrados sigan
    apuntando al contenido con el que se corrieron.

    Es la diferencia con el esquema anterior, que hacía *upsert* por título: allí
    una corrección del enunciado invalidaba mediciones previas sin dejar rastro.
    """
    try:
        definiciones = cargar_directorio(directorio)
    except ErrorDeBanco as exc:
        print(f"✗ {exc}")
        return 1

    problematicas = [d for d in definiciones if d.advertencias()]
    if problematicas and not forzar:
        print("No se sembró: hay instancias con advertencias de diseño.\n")
        for definicion in problematicas:
            print(f"  {definicion.codigo}:")
            for advertencia in definicion.advertencias():
                print(f"    ↳ {advertencia}")
        print("\nCorregilas, o volvé a correr con --forzar si son deliberadas.")
        return 1

    nuevas = actualizadas = sin_cambios = 0

    with sesion_de_trabajo() as sesion:
        for definicion in definiciones:
            vigente = sesion.scalar(
                select(Instancia).where(
                    Instancia.codigo == definicion.codigo, Instancia.activa.is_(True)
                )
            )

            if vigente is not None and vigente.hash_contenido == definicion.hash_contenido:
                # El contenido sustantivo no cambió: se refrescan sólo los campos
                # que no afectan ninguna medición.
                vigente.titulo = definicion.titulo
                vigente.subtema = definicion.subtema
                vigente.dificultad_declarada = definicion.dificultad_declarada
                vigente.resolucion_latex = definicion.resolucion_latex
                vigente.estructura_solucion = serializar_estructura(definicion.estructura)
                sin_cambios += 1
                continue

            version = 1
            if vigente is not None:
                vigente.activa = False
                version = vigente.version + 1
                actualizadas += 1
            else:
                nuevas += 1

            sesion.add(
                Instancia(
                    codigo=definicion.codigo,
                    version=version,
                    hash_contenido=definicion.hash_contenido,
                    titulo=definicion.titulo,
                    area=definicion.area,
                    subtema=definicion.subtema,
                    dificultad_declarada=definicion.dificultad_declarada,
                    enunciado_publico=definicion.enunciado_publico,
                    dato_a=definicion.dato_a,
                    dato_b=definicion.dato_b,
                    respuesta_canonica=definicion.respuesta_canonica,
                    tipo_respuesta=definicion.tipo_respuesta,
                    resolucion_latex=definicion.resolucion_latex,
                    estructura_solucion=serializar_estructura(definicion.estructura),
                )
            )
            marca = "+" if vigente is None else "↑"
            print(f"  {marca} {definicion.codigo} (v{version})")

    print(
        f"\n{nuevas} nueva(s), {actualizadas} versión(es) nueva(s) por cambio de "
        f"contenido, {sin_cambios} sin cambios."
    )
    if actualizadas:
        print(
            "Las instancias con versión nueva necesitan recalibrarse: sus "
            "mediciones anteriores describen otro contenido."
        )
    return 0
