"""Arnés del solver de referencia: estimación empírica de la competencia.

Este módulo es lo que convierte la interdependencia epistémica de una
afirmación de diseño en una medición. En vez de postular que "el dato A solo no
alcanza", se corre un solver declarado ``N`` veces con sólo ese dato y se cuenta
cuántas veces acierta.

El procedimiento es caro —cuatro celdas por ``N`` ejecuciones por instancia— y
por eso corre fuera del ciclo interactivo, desde la línea de comandos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cps.agentes.motor import Mensaje, MotorModelos
from cps.agentes.protocolo import prompt_solver
from cps.dominio.indicadores import Celda, Competencia
from cps.dominio.verificacion import (
    TipoRespuesta,
    Veredicto,
    extraer_respuesta_final,
    verificar,
)

__all__ = ["EjecucionIndividual", "ResultadoCalibracion", "calibrar_instancia"]

# Qué datos privados ve el solver en cada celda.
DATOS_POR_CELDA: dict[Celda, tuple[bool, bool]] = {
    Celda.VACIA: (False, False),
    Celda.SOLO_A: (True, False),
    Celda.SOLO_B: (False, True),
    Celda.AMBOS: (True, True),
}


@dataclass(frozen=True, slots=True)
class EjecucionIndividual:
    """El resultado de una única ejecución del solver."""

    celda: Celda
    indice: int
    respuesta_cruda: str
    respuesta_extraida: str | None
    veredicto: Veredicto
    acerto: bool
    tokens_entrada: int | None
    tokens_salida: int | None
    latencia_ms: int | None


@dataclass(frozen=True, slots=True)
class ResultadoCalibracion:
    """Todas las ejecuciones de una instancia más la competencia agregada."""

    ejecuciones: list[EjecucionIndividual]
    competencia: Competencia
    ensayos_por_celda: int

    def aciertos(self, celda: Celda) -> int:
        return sum(1 for e in self.ejecuciones if e.celda is celda and e.acerto)

    def no_parseables(self, celda: Celda) -> int:
        """Ejecuciones que no se pudieron interpretar.

        Si son muchas, la estimación de esa celda está sesgada hacia abajo y no
        debe leerse como insuficiencia informativa: es un fallo del instrumento.
        """
        return sum(
            1
            for e in self.ejecuciones
            if e.celda is celda and e.veredicto in (Veredicto.NO_PARSEABLE, Veredicto.SIN_RESPUESTA)
        )

    def advertencias(self) -> list[str]:
        """Problemas detectados durante la calibración."""
        problemas: list[str] = []

        for celda in Celda:
            fallidas = self.no_parseables(celda)
            if fallidas > self.ensayos_por_celda * 0.2:
                problemas.append(
                    f"En la celda {celda.value} no se pudo interpretar la respuesta "
                    f"en {fallidas} de {self.ensayos_por_celda} ejecuciones: la "
                    "estimación está sesgada hacia abajo."
                )

        if self.competencia.viola_monotonia:
            problemas.append(
                "Se viola la monotonía informacional: alguna celda con más datos "
                "acierta menos que una con menos. Revisar si el enunciado o los "
                "datos inducen a error."
            )

        if self.competencia.vacia > 0.15:
            problemas.append(
                f"El solver acierta el {self.competencia.vacia:.0%} de las veces sin "
                "ningún dato privado. O el enunciado filtra la respuesta, o la "
                "instancia está contaminada en el corpus de entrenamiento."
            )

        if self.competencia.es_degenerada:
            problemas.append(
                "La ganancia alcanzable es nula: la instancia no admite "
                "indicadores normalizados."
            )
        elif self.competencia.ambos < 0.5:
            problemas.append(
                f"Con ambos datos el solver sólo acierta el {self.competencia.ambos:.0%}: "
                "la instancia puede ser demasiado difícil para medir con este solver."
            )

        return problemas


def calibrar_instancia(
    *,
    motor: MotorModelos,
    area: str,
    enunciado: str,
    dato_a: str,
    dato_b: str,
    respuesta_canonica: str,
    tipo_respuesta: TipoRespuesta = TipoRespuesta.EXPRESION,
    ensayos_por_celda: int = 30,
    modelo: str | None = None,
    esfuerzo: str | None = None,
    al_avanzar: Callable[[Celda, int, int], None] | None = None,
) -> ResultadoCalibracion:
    """Estima la función de competencia de una instancia.

    Corre el solver ``ensayos_por_celda`` veces sobre cada una de las cuatro
    celdas de información y verifica cada respuesta contra la clave canónica.

    Parameters
    ----------
    al_avanzar:
        Callback opcional ``(celda, hechas, total)`` para reportar progreso.
        La calibración completa son ``4 * ensayos_por_celda`` llamadas, que con
        30 ensayos son 120 por instancia: conviene poder ver que avanza.

    Returns
    -------
    El resultado con todas las ejecuciones individuales conservadas. No se
    descartan: inspeccionar los aciertos de las celdas individuales es la forma
    de detectar contaminación.
    """
    ejecuciones: list[EjecucionIndividual] = []
    aciertos: dict[Celda, int] = {}

    for celda in Celda:
        incluye_a, incluye_b = DATOS_POR_CELDA[celda]
        disponibles = [d for d, incluir in ((dato_a, incluye_a), (dato_b, incluye_b)) if incluir]
        plantilla = prompt_solver(area=area, enunciado=enunciado, datos_disponibles=disponibles)

        aciertos_celda = 0
        for indice in range(ensayos_por_celda):
            respuesta = motor.completar(
                sistema=plantilla.texto,
                mensajes=[Mensaje(rol="user", contenido="Resolvé el problema.")],
                modelo=modelo,
                esfuerzo=esfuerzo,
            )

            extraida = extraer_respuesta_final(respuesta.texto)
            resultado = verificar(extraida, respuesta_canonica, tipo_respuesta)

            ejecuciones.append(
                EjecucionIndividual(
                    celda=celda,
                    indice=indice,
                    respuesta_cruda=respuesta.texto,
                    respuesta_extraida=extraida,
                    veredicto=resultado.veredicto,
                    acerto=resultado.es_correcto,
                    tokens_entrada=respuesta.tokens_entrada,
                    tokens_salida=respuesta.tokens_salida,
                    latencia_ms=respuesta.latencia_ms,
                )
            )
            if resultado.es_correcto:
                aciertos_celda += 1

            if al_avanzar is not None:
                al_avanzar(celda, indice + 1, ensayos_por_celda)

        aciertos[celda] = aciertos_celda

    competencia = Competencia(
        vacia=aciertos[Celda.VACIA] / ensayos_por_celda,
        solo_a=aciertos[Celda.SOLO_A] / ensayos_por_celda,
        solo_b=aciertos[Celda.SOLO_B] / ensayos_por_celda,
        ambos=aciertos[Celda.AMBOS] / ensayos_por_celda,
        ensayos_por_celda=ensayos_por_celda,
    )

    return ResultadoCalibracion(
        ejecuciones=ejecuciones,
        competencia=competencia,
        ensayos_por_celda=ensayos_por_celda,
    )
