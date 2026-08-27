"""Calibración: estimación empírica de la función de competencia.

Es el procedimiento más caro del protocolo. Con la configuración por defecto son
cuatro celdas por treinta ejecuciones, es decir 120 llamadas al modelo por
instancia. Corre desde la línea de comandos y no desde la interfaz, para que sea
un acto deliberado y registrable.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from cps.agentes.motor import MotorModelos
from cps.agentes.solver import calibrar_instancia
from cps.config import obtener_config
from cps.db import sesion_de_trabajo
from cps.dominio.areas import nombre_area
from cps.dominio.indicadores import Celda, PerfilDiseno, intervalo_wilson
from cps.dominio.verificacion import TipoRespuesta
from cps.modelos.entidades import EjecucionSolver, Instancia, MedicionDiseno
from cps.servicios.banco import cargar_estructura


def calibrar(
    *,
    codigos: list[str] | None = None,
    ensayos: int | None = None,
    recalcular: bool = False,
    permitir_simulado: bool = False,
) -> int:
    config = obtener_config()
    motor = MotorModelos(config)

    if motor.simulado and not permitir_simulado:
        print(
            "No hay credencial de modelo configurada. Una calibración simulada no "
            "produce mediciones válidas.\n"
            "Configurá ANTHROPIC_API_KEY, o volvé a correr con --permitir-simulado "
            "si sólo querés ejercitar el circuito.",
            file=sys.stderr,
        )
        return 1

    ensayos_efectivos = ensayos or config.ensayos_por_celda
    huella = config.huella_experimental()

    with sesion_de_trabajo() as sesion:
        consulta = select(Instancia).where(Instancia.activa.is_(True))
        if codigos:
            consulta = consulta.where(Instancia.codigo.in_(codigos))
        instancias = sesion.scalars(consulta.order_by(Instancia.codigo)).all()

        if not instancias:
            print("No hay instancias que calibrar.", file=sys.stderr)
            return 1

        pendientes = []
        for instancia in instancias:
            ya_medida = sesion.scalar(
                select(MedicionDiseno).where(
                    MedicionDiseno.instancia_id == instancia.id,
                    MedicionDiseno.huella_experimental == huella,
                    MedicionDiseno.hash_contenido == instancia.hash_contenido,
                )
            )
            if ya_medida is not None and not recalcular:
                continue
            pendientes.append(instancia)

        if not pendientes:
            print("Todas las instancias ya están calibradas con la huella vigente.")
            print("Usá --recalcular para volver a medirlas.")
            return 0

        total_llamadas = len(pendientes) * 4 * ensayos_efectivos
        print(
            f"Calibrando {len(pendientes)} instancia(s) con {ensayos_efectivos} "
            f"ensayos por celda.\nHuella experimental: {huella}\n"
            f"Total de llamadas al modelo: {total_llamadas}\n"
        )

        # El retorno de carro sólo tiene sentido en una terminal; redirigido a un
        # archivo dejaría una única línea ilegible con todo el progreso.
        interactivo = sys.stdout.isatty()

        def progreso(celda: Celda, hechas: int, total: int) -> None:
            if interactivo:
                print(f"\r    {celda.value:8} {hechas}/{total}", end="", flush=True)
            elif hechas == total:
                print(f"    {celda.value:8} {total}/{total}")

        for numero, instancia in enumerate(pendientes, start=1):
            print(f"[{numero}/{len(pendientes)}] {instancia.codigo} — {instancia.titulo}")

            resultado = calibrar_instancia(
                motor=motor,
                area=nombre_area(instancia.area),
                enunciado=instancia.enunciado_publico,
                dato_a=instancia.dato_a,
                dato_b=instancia.dato_b,
                respuesta_canonica=instancia.respuesta_canonica,
                tipo_respuesta=TipoRespuesta(instancia.tipo_respuesta),
                ensayos_por_celda=ensayos_efectivos,
                modelo=config.modelo_solver,
                esfuerzo=config.esfuerzo_solver,
                al_avanzar=progreso,
            )
            if interactivo:
                print("\r" + " " * 40, end="\r")

            _guardar_ejecuciones(sesion, instancia, resultado, config, huella)
            medicion = _guardar_medicion(sesion, instancia, resultado, huella)
            _informar(instancia, resultado, medicion)

    return 0


def _guardar_ejecuciones(sesion, instancia, resultado, config, huella) -> None:
    """Persiste cada ejecución individual.

    No se guardan sólo los agregados: inspeccionar los casos en que el solver
    acierta con un único dato es la forma de detectar contaminación del corpus
    de entrenamiento, y eso requiere tener las respuestas crudas.
    """
    for ejecucion in resultado.ejecuciones:
        sesion.add(
            EjecucionSolver(
                instancia_id=instancia.id,
                celda=ejecucion.celda.value,
                indice_replica=ejecucion.indice,
                modelo=config.modelo_solver,
                esfuerzo=config.esfuerzo_solver,
                huella_experimental=huella,
                respuesta_cruda=ejecucion.respuesta_cruda,
                respuesta_extraida=ejecucion.respuesta_extraida,
                veredicto=ejecucion.veredicto.value,
                acerto=ejecucion.acerto,
                tokens_entrada=ejecucion.tokens_entrada,
                tokens_salida=ejecucion.tokens_salida,
                latencia_ms=ejecucion.latencia_ms,
            )
        )


def _guardar_medicion(sesion, instancia, resultado, huella) -> MedicionDiseno:
    competencia = resultado.competencia
    advertencias = list(resultado.advertencias())

    estructura = cargar_estructura(instancia.estructura_solucion)
    advertencias.extend(estructura.verificar_particion_genuina())

    if competencia.es_degenerada:
        # Sin ganancia alcanzable los indicadores normalizados no existen. Se
        # registra la medición igual, con los indicadores en cero y la
        # advertencia, en vez de perder el trabajo de calibración.
        interdependencia = balance = 0.0
        error_balance = None
    else:
        interdependencia = competencia.interdependencia()
        balance = competencia.balance_carga()
        error_balance = competencia.error_estandar_balance()

    existente = sesion.scalar(
        select(MedicionDiseno).where(
            MedicionDiseno.instancia_id == instancia.id,
            MedicionDiseno.huella_experimental == huella,
        )
    )
    medicion = existente or MedicionDiseno(
        instancia_id=instancia.id, huella_experimental=huella
    )

    medicion.hash_contenido = instancia.hash_contenido
    medicion.v_vacia = competencia.vacia
    medicion.v_solo_a = competencia.solo_a
    medicion.v_solo_b = competencia.solo_b
    medicion.v_ambos = competencia.ambos
    medicion.ensayos_por_celda = resultado.ensayos_por_celda
    medicion.interdependencia = interdependencia
    medicion.balance_carga = balance
    medicion.emergencia = estructura.emergencia()
    medicion.rondas_minimas = estructura.rondas_minimas()
    medicion.dificultad = competencia.dificultad()
    medicion.error_estandar_balance = error_balance
    medicion.monotonia_violada = competencia.viola_monotonia
    medicion.advertencias = advertencias

    sesion.add(medicion)
    return medicion


def _informar(instancia, resultado, medicion) -> None:
    competencia = resultado.competencia
    n = resultado.ensayos_por_celda

    print(f"    competencia por celda (aciertos/{n}, IC 95%):")
    for celda, valor in (
        (Celda.VACIA, competencia.vacia),
        (Celda.SOLO_A, competencia.solo_a),
        (Celda.SOLO_B, competencia.solo_b),
        (Celda.AMBOS, competencia.ambos),
    ):
        aciertos = resultado.aciertos(celda)
        bajo, alto = intervalo_wilson(aciertos, n)
        print(f"      {celda.value:8} {aciertos:3}/{n}  {valor:.3f}  [{bajo:.3f}, {alto:.3f}]")

    if competencia.es_degenerada:
        print("    ⚠ instancia degenerada: sin ganancia alcanzable")
    else:
        perfil = PerfilDiseno.desde_competencia(
            competencia,
            emergencia=medicion.emergencia,
            rondas_minimas=medicion.rondas_minimas,
        )
        print(
            f"    IE={perfil.interdependencia:.3f}  IBC={perfil.balance_carga:.3f}  "
            f"MEE={perfil.emergencia:.2f}  t_min={perfil.rondas_minimas}  "
            f"dificultad={perfil.dificultad:.2f}"
        )
        print(
            "    criterio de diseño: "
            + ("cumple" if perfil.cumple_criterio_de_diseno() else "NO cumple")
        )

    for advertencia in medicion.advertencias:
        print(f"    ⚠ {advertencia}")
    print()
