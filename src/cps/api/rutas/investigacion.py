"""Endpoints reservados a investigadores: estado del banco y exportación."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from cps.api import esquemas
from cps.api.seguridad import investigador_actual
from cps.config import Configuracion, obtener_config
from cps.db import obtener_sesion
from cps.modelos.entidades import (
    Codificacion,
    Cuenta,
    Episodio,
    Instancia,
    MedicionDiseno,
    Modalidad,
)

router = APIRouter(prefix="/api/investigacion", tags=["investigación"])


@router.get("/banco", response_model=esquemas.ResumenBanco)
def estado_del_banco(
    sesion: Session = Depends(obtener_sesion),
    config: Configuracion = Depends(obtener_config),
    _: Cuenta = Depends(investigador_actual),
) -> esquemas.ResumenBanco:
    """Estado del banco desde el punto de vista del protocolo.

    Informa cuántas instancias están calibradas bajo la huella experimental
    vigente, que no es lo mismo que cuántas tienen alguna medición: si el solver
    de referencia cambió, las mediciones anteriores describen otra escala.
    """
    huella = config.huella_experimental()

    instancias = sesion.scalars(
        select(Instancia).options(selectinload(Instancia.mediciones)).where(Instancia.activa.is_(True))
    ).all()

    calibradas = 0
    cumplen = 0
    con_advertencias = 0
    for instancia in instancias:
        medicion = next(
            (m for m in instancia.mediciones if m.huella_experimental == huella), None
        )
        if medicion is None:
            continue
        calibradas += 1
        if medicion.advertencias:
            con_advertencias += 1
        if (
            medicion.interdependencia >= 0.8
            and medicion.rondas_minimas >= 2
            and not medicion.monotonia_violada
        ):
            cumplen += 1

    por_modalidad = dict(
        sesion.execute(
            select(Episodio.modalidad, func.count(Episodio.id)).group_by(Episodio.modalidad)
        ).all()
    )
    simulados = sesion.scalar(
        select(func.count(Episodio.id)).where(Episodio.simulado.is_(True))
    )

    return esquemas.ResumenBanco(
        total_instancias=len(instancias),
        calibradas=calibradas,
        sin_calibrar=len(instancias) - calibradas,
        cumplen_criterio=cumplen,
        con_advertencias=con_advertencias,
        episodios_por_modalidad={str(k): v for k, v in por_modalidad.items()},
        episodios_simulados=int(simulados or 0),
        huella_experimental=huella,
    )


@router.get("/mediciones")
def listar_mediciones(
    sesion: Session = Depends(obtener_sesion),
    huella: str | None = None,
    _: Cuenta = Depends(investigador_actual),
) -> list[dict]:
    """Perfiles de diseño con las competencias crudas por celda.

    A diferencia del catálogo, acá sí se exponen los ``v(S)``: son el insumo del
    análisis y quien consulta este endpoint ya tiene acceso al banco completo.
    """
    consulta = select(MedicionDiseno).options(selectinload(MedicionDiseno.instancia))
    if huella:
        consulta = consulta.where(MedicionDiseno.huella_experimental == huella)

    mediciones = sesion.scalars(consulta.order_by(MedicionDiseno.instancia_id)).all()
    return [
        {
            "instancia_id": m.instancia_id,
            "codigo": m.instancia.codigo if m.instancia else None,
            "area": m.instancia.area if m.instancia else None,
            "huella_experimental": m.huella_experimental,
            "hash_contenido": m.hash_contenido,
            "contenido_vigente": bool(
                m.instancia and m.hash_contenido == m.instancia.hash_contenido
            ),
            "competencia": {
                "vacia": m.v_vacia,
                "solo_a": m.v_solo_a,
                "solo_b": m.v_solo_b,
                "ambos": m.v_ambos,
                "ensayos_por_celda": m.ensayos_por_celda,
            },
            "perfil": {
                "interdependencia": m.interdependencia,
                "balance_carga": m.balance_carga,
                "emergencia": m.emergencia,
                "rondas_minimas": m.rondas_minimas,
                "dificultad": m.dificultad,
            },
            "error_estandar_balance": m.error_estandar_balance,
            "monotonia_violada": m.monotonia_violada,
            "advertencias": m.advertencias,
            "calculada_en": m.calculada_en.isoformat() if m.calculada_en else None,
        }
        for m in mediciones
    ]


def _filas_episodios(
    sesion: Session, *, incluir_simulados: bool, incluir_transcripts: bool
) -> Iterator[dict]:
    """Genera las filas de la exportación, una por episodio.

    Es un generador para que la exportación no cargue todo en memoria: con miles
    de episodios y transcripts completos, materializar la lista entera sería
    innecesariamente costoso.
    """
    consulta = (
        select(Episodio)
        .options(
            selectinload(Episodio.instancia),
            selectinload(Episodio.turnos),
            selectinload(Episodio.codificaciones),
            selectinload(Episodio.cuenta),
        )
        .where(Episodio.modalidad != Modalidad.RESOLUCION_DIRECTA)
        .order_by(Episodio.id)
    )
    if not incluir_simulados:
        consulta = consulta.where(Episodio.simulado.is_(False))

    for episodio in sesion.scalars(consulta):
        fila = {
            "episodio_id": episodio.id,
            # Seudónimo, nunca el correo: es lo que hace exportable el archivo.
            "participante": episodio.cuenta.seudonimo if episodio.cuenta else None,
            "instancia_codigo": episodio.instancia.codigo if episodio.instancia else None,
            "instancia_version": episodio.instancia.version if episodio.instancia else None,
            "area": episodio.instancia.area if episodio.instancia else None,
            "modalidad": episodio.modalidad,
            "condicion_divulgacion": episodio.condicion_divulgacion,
            "lado_humano": episodio.lado_humano,
            "modelo_participante": episodio.modelo_participante,
            "huella_experimental": episodio.huella_experimental,
            "semilla": episodio.semilla,
            "simulado": episodio.simulado,
            "estado": episodio.estado,
            "turnos_usados": episodio.turnos_usados,
            "veredicto": episodio.veredicto,
            "acerto": episodio.acerto,
            "turno_divulgacion_a": episodio.turno_divulgacion_a,
            "turno_divulgacion_b": episodio.turno_divulgacion_b,
            "divulgacion_prematura": episodio.divulgacion_prematura,
            "tokens_totales": sum(
                (t.tokens_salida or 0) + (t.tokens_entrada or 0) for t in episodio.turnos
            ),
            "latencia_total_ms": sum(t.latencia_ms or 0 for t in episodio.turnos),
            "iniciado_en": episodio.iniciado_en.isoformat() if episodio.iniciado_en else None,
            "finalizado_en": (
                episodio.finalizado_en.isoformat() if episodio.finalizado_en else None
            ),
            "codificaciones": [
                {
                    "codificador": c.codificador,
                    "es_humano": c.es_humano,
                    "pasada": c.pasada,
                    "indice_calidad": c.indice_calidad,
                    "puntajes": c.puntajes,
                    "modalidad_adivinada": c.modalidad_adivinada,
                }
                for c in episodio.codificaciones
            ],
        }

        if incluir_transcripts:
            fila["turnos"] = [
                {
                    "orden": t.orden,
                    "rol": t.rol,
                    "tipo_autor": t.tipo_autor,
                    "contenido": t.contenido,
                    "tokens_entrada": t.tokens_entrada,
                    "tokens_salida": t.tokens_salida,
                    "latencia_ms": t.latencia_ms,
                }
                for t in episodio.turnos
            ]

        yield fila


@router.get("/exportacion.jsonl")
def exportar(
    sesion: Session = Depends(obtener_sesion),
    incluir_simulados: bool = Query(
        False, description="Los episodios simulados no son dato experimental."
    ),
    incluir_transcripts: bool = Query(True),
    _: Cuenta = Depends(investigador_actual),
) -> StreamingResponse:
    """Exportación en JSON por líneas, seudonimizada.

    Se excluyen por defecto los episodios simulados y siempre los de consulta de
    resolución, que no son observaciones del estudio.
    """

    def generar() -> Iterator[str]:
        for fila in _filas_episodios(
            sesion,
            incluir_simulados=incluir_simulados,
            incluir_transcripts=incluir_transcripts,
        ):
            yield json.dumps(fila, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generar(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="episodios.jsonl"'},
    )


@router.get("/desenmascaramiento")
def control_de_ceguera(
    sesion: Session = Depends(obtener_sesion), _: Cuenta = Depends(investigador_actual)
) -> dict:
    """Con qué frecuencia los jueces identifican la modalidad que codificaron.

    Con dos modalidades el azar da 0.5. Un valor sustancialmente mayor indica que
    la ceguera falló y que los puntajes pueden estar contaminados por el
    conocimiento de la condición.
    """
    from cps.agentes.juez import tasa_de_desenmascaramiento

    filas = sesion.execute(
        select(Codificacion.codificador, Codificacion.modalidad_adivinada, Episodio.modalidad)
        .join(Episodio, Codificacion.episodio_id == Episodio.id)
        .where(Codificacion.es_humano.is_(False))
    ).all()

    por_juez: dict[str, list[tuple[str | None, str]]] = {}
    for codificador, adivinada, real in filas:
        por_juez.setdefault(codificador, []).append((adivinada, real))

    return {
        "azar": 0.5,
        "por_codificador": {
            codificador: {
                "n_con_respuesta": sum(
                    1 for a, _ in pares if a not in (None, "no_se", "")
                ),
                "tasa_acierto": tasa_de_desenmascaramiento(
                    [a for a, _ in pares], [r for _, r in pares]
                ),
            }
            for codificador, pares in por_juez.items()
        },
    }
