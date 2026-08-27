"""Codificación de transcripts y análisis de divulgación."""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cps.agentes.juez import codificar_episodio, localizar_divulgacion
from cps.agentes.motor import MotorModelos
from cps.config import obtener_config
from cps.db import sesion_de_trabajo
from cps.modelos.entidades import (
    Codificacion,
    Episodio,
    EstadoEpisodio,
    Modalidad,
)
from cps.servicios.episodios import historial_de


def _motor_o_error(permitir_simulado: bool) -> MotorModelos | None:
    config = obtener_config()
    motor = MotorModelos(config)
    if motor.simulado and not permitir_simulado:
        print(
            "No hay credencial de modelo configurada. Una codificación simulada no "
            "tiene valor experimental.\nUsá --permitir-simulado sólo para probar el "
            "circuito.",
            file=sys.stderr,
        )
        return None
    return motor


def _episodios_de_estudio(sesion, limite: int | None):
    """Episodios que son observaciones del estudio.

    Excluye la consulta de resolución, que no es una modalidad, y los episodios
    simulados, que no son dato experimental.
    """
    consulta = (
        select(Episodio)
        .options(selectinload(Episodio.turnos), selectinload(Episodio.instancia))
        .where(
            Episodio.modalidad != Modalidad.RESOLUCION_DIRECTA,
            Episodio.simulado.is_(False),
            Episodio.estado != EstadoEpisodio.EN_CURSO,
        )
        .order_by(Episodio.id)
    )
    if limite:
        consulta = consulta.limit(limite)
    return sesion.scalars(consulta).all()


def codificar(
    *, limite: int | None = None, recodificar: bool = False, permitir_simulado: bool = False
) -> int:
    """Codifica cada episodio con todos los jueces configurados.

    Se usan varios jueces de familias distintas a propósito: el acuerdo entre
    ellos, y con la submuestra codificada por humanos, es lo único que sostiene
    la validez de la codificación automática.
    """
    motor = _motor_o_error(permitir_simulado)
    if motor is None:
        return 1

    config = obtener_config()

    with sesion_de_trabajo() as sesion:
        episodios = _episodios_de_estudio(sesion, limite)
        if not episodios:
            print("No hay episodios cerrados para codificar.")
            return 0

        print(
            f"Codificando {len(episodios)} episodio(s) con "
            f"{len(config.modelos_juez)} juez/jueces: {', '.join(config.modelos_juez)}\n"
        )

        hechas = omitidas = fallidas = 0

        for episodio in episodios:
            historial = historial_de(episodio)
            for juez in config.modelos_juez:
                existente = sesion.scalar(
                    select(Codificacion).where(
                        Codificacion.episodio_id == episodio.id,
                        Codificacion.codificador == juez,
                        Codificacion.pasada == 1,
                    )
                )
                if existente is not None and not recodificar:
                    omitidas += 1
                    continue

                resultado = codificar_episodio(
                    motor=motor,
                    historial=historial,
                    codificador=juez,
                    esfuerzo=config.esfuerzo_juez,
                )

                if not resultado.es_valida:
                    fallidas += 1
                    print(f"  ✗ ep{episodio.id} [{juez}]: {resultado.error}")
                    continue

                registro = existente or Codificacion(
                    episodio_id=episodio.id, codificador=juez, pasada=1
                )
                registro.es_humano = False
                registro.puntajes = {
                    codigo: int(nivel) for codigo, nivel in resultado.vector.puntajes.items()
                }
                registro.indice_calidad = resultado.vector.indice_calidad()
                registro.modalidad_adivinada = resultado.modalidad_adivinada
                registro.justificacion = resultado.justificacion
                registro.tokens_entrada = resultado.tokens_entrada
                registro.tokens_salida = resultado.tokens_salida
                sesion.add(registro)

                hechas += 1
                print(f"  · ep{episodio.id} [{juez}] CQI={registro.indice_calidad:.3f}")

    print(f"\n{hechas} codificación(es) nueva(s), {omitidas} ya existentes, {fallidas} fallidas.")
    if fallidas:
        print("Las fallidas quedan sin registrar: son dato faltante, no ceros.")
    return 0


def analizar_divulgacion(*, limite: int | None = None, permitir_simulado: bool = False) -> int:
    """Determina en qué turno cada dato privado quedó recuperable del transcript.

    Es la medición de la conducta que el protocolo decidió observar en lugar de
    prohibir: un valor 1 indica que el participante colapsó la partición en su
    primer mensaje.
    """
    motor = _motor_o_error(permitir_simulado)
    if motor is None:
        return 1

    config = obtener_config()

    with sesion_de_trabajo() as sesion:
        episodios = [
            e
            for e in _episodios_de_estudio(sesion, limite)
            if e.turno_divulgacion_a is None and e.turno_divulgacion_b is None
        ]
        if not episodios:
            print("No hay episodios pendientes de análisis de divulgación.")
            return 0

        print(f"Analizando divulgación en {len(episodios)} episodio(s).\n")
        prematuros = 0

        for episodio in episodios:
            historial = historial_de(episodio)
            instancia = episodio.instancia

            episodio.turno_divulgacion_a = localizar_divulgacion(
                motor=motor,
                historial=historial,
                dato_privado=instancia.dato_a,
                modelo=config.modelos_juez[0],
            )
            episodio.turno_divulgacion_b = localizar_divulgacion(
                motor=motor,
                historial=historial,
                dato_privado=instancia.dato_b,
                modelo=config.modelos_juez[0],
            )

            if episodio.divulgacion_prematura:
                prematuros += 1
            print(
                f"  · ep{episodio.id} [{episodio.modalidad}] "
                f"A={episodio.turno_divulgacion_a} B={episodio.turno_divulgacion_b}"
            )

        print(
            f"\n{prematuros} de {len(episodios)} episodio(s) con divulgación en el "
            f"primer turno ({prematuros / len(episodios):.0%})."
        )
    return 0
