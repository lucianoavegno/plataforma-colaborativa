"""Codificación automática de la calidad del proceso.

Codificar a mano doce celdas por transcript no escala a cientos de episodios,
así que la codificación la hacen modelos jueces. Eso traslada el problema: ahora
hay que establecer que el juez mide lo que dice medir.

Las tres precauciones que implementa este módulo:

* **Ceguera**: el juez recibe el transcript con roles neutros y sin saber qué
  modalidad ni qué condición observó.
* **Desenmascaramiento**: se le pregunta igual qué modalidad cree haber visto.
  Si acierta por encima del azar, la ceguera falló y hay que reportarlo en lugar
  de suponerla.
* **Pluralidad**: se codifica con jueces de familias distintas, y el acuerdo
  entre ellos y con anotadores humanos es lo que sostiene la validez.

Ninguna de las tres convierte al juez en un instrumento perfecto. Lo que hacen
es volver medible cuánto se le puede creer.
"""

from __future__ import annotations

from dataclasses import dataclass

from cps.agentes.dialogo import TurnoDialogo, transcripcion_numerada
from cps.agentes.motor import Mensaje, MotorModelos
from cps.agentes.protocolo import normalizar_estilo, prompt_divulgacion, prompt_juez
from cps.dominio.rubrica import CODIGO_A_CELDA, VectorCalidad, acuerdo_ordinal

__all__ = [
    "ResultadoCodificacion",
    "acuerdo_entre_codificaciones",
    "codificar_episodio",
    "localizar_divulgacion",
    "tasa_de_desenmascaramiento",
]


@dataclass(frozen=True, slots=True)
class ResultadoCodificacion:
    """Codificación producida por un juez, con su control de ceguera."""

    codificador: str
    vector: VectorCalidad | None
    modalidad_adivinada: str | None
    justificacion: str | None
    tokens_entrada: int | None
    tokens_salida: int | None
    error: str | None = None

    @property
    def es_valida(self) -> bool:
        return self.vector is not None

    @property
    def indice_calidad(self) -> float | None:
        return self.vector.indice_calidad() if self.vector else None


def codificar_episodio(
    *,
    motor: MotorModelos,
    historial: list[TurnoDialogo],
    codificador: str,
    esfuerzo: str | None = None,
) -> ResultadoCodificacion:
    """Codifica un transcript con un juez, en condiciones de ceguera.

    El transcript se normaliza estilísticamente y se presenta con roles neutros.
    Un fallo de formato del juez devuelve un resultado inválido en lugar de
    lanzar excepción: es un dato sobre el juez y conviene registrarlo.
    """
    texto = normalizar_estilo(transcripcion_numerada(historial, anonimizar=True))
    plantilla = prompt_juez()

    datos, respuesta = motor.completar_json(
        sistema=plantilla.texto,
        mensajes=[Mensaje(rol="user", contenido=f"TRANSCRIPCIÓN:\n\n{texto}")],
        modelo=codificador,
        esfuerzo=esfuerzo,
    )

    if datos is None:
        return ResultadoCodificacion(
            codificador=codificador,
            vector=None,
            modalidad_adivinada=None,
            justificacion=None,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            error="El juez no devolvió un objeto JSON interpretable",
        )

    try:
        vector = VectorCalidad.desde_dict(_completar_celdas(datos.get("puntajes", {})))
    except ValueError as exc:
        return ResultadoCodificacion(
            codificador=codificador,
            vector=None,
            modalidad_adivinada=datos.get("modalidad_adivinada"),
            justificacion=datos.get("justificacion"),
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            error=f"Puntajes inválidos: {exc}",
        )

    return ResultadoCodificacion(
        codificador=codificador,
        vector=vector,
        modalidad_adivinada=datos.get("modalidad_adivinada"),
        justificacion=datos.get("justificacion"),
        tokens_entrada=respuesta.tokens_entrada,
        tokens_salida=respuesta.tokens_salida,
    )


def _completar_celdas(puntajes: object) -> dict[str, int]:
    """Valida las claves recibidas del juez y exige las doce celdas.

    No se rellenan las faltantes con ceros: un juez que omite celdas produjo una
    codificación incompleta, y tratarla como "todo ausente" inventaría datos.
    """
    if not isinstance(puntajes, dict):
        raise ValueError("El campo 'puntajes' no es un objeto")

    limpios: dict[str, int] = {}
    for codigo, valor in puntajes.items():
        clave = str(codigo).strip().upper()
        if clave not in CODIGO_A_CELDA:
            continue
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            raise ValueError(f"El puntaje de {clave} no es numérico: {valor!r}")
        limpios[clave] = int(valor)
    return limpios


def localizar_divulgacion(
    *,
    motor: MotorModelos,
    historial: list[TurnoDialogo],
    dato_privado: str,
    modelo: str | None = None,
) -> int | None:
    """Determina en qué turno un dato privado quedó recuperable del transcript.

    Devuelve ``None`` si nunca se volcó por completo. El valor 1 indica que el
    participante colapsó la partición en su primer mensaje, que es la conducta
    que el estudio quiere medir en lugar de prohibir.
    """
    texto = transcripcion_numerada(historial, anonimizar=True)
    plantilla = prompt_divulgacion(dato_privado, texto)

    datos, _ = motor.completar_json(
        sistema=plantilla.texto,
        mensajes=[Mensaje(rol="user", contenido="¿En qué turno?")],
        modelo=modelo,
    )
    if datos is None:
        return None

    turno = datos.get("turno")
    if turno is None or isinstance(turno, bool):
        return None
    try:
        valor = int(turno)
    except (TypeError, ValueError):
        return None
    return valor if valor >= 1 else None


def tasa_de_desenmascaramiento(
    adivinanzas: list[str | None], modalidades_reales: list[str]
) -> float:
    """Proporción de aciertos del juez al identificar la modalidad.

    Con dos modalidades, el azar da 0.5. Un valor sustancialmente mayor indica
    que la ceguera falló y que los puntajes pueden estar contaminados por el
    conocimiento de la condición.

    Las respuestas ``"no_se"`` o nulas se excluyen del denominador: son
    abstenciones, no errores.
    """
    if len(adivinanzas) != len(modalidades_reales):
        raise ValueError("Las listas deben tener la misma longitud")

    pares = [
        (adivinanza, real)
        for adivinanza, real in zip(adivinanzas, modalidades_reales, strict=True)
        if adivinanza not in (None, "no_se", "")
    ]
    if not pares:
        return 0.0
    return sum(1 for adivinanza, real in pares if adivinanza == real) / len(pares)


def acuerdo_entre_codificaciones(
    codificacion_a: list[VectorCalidad], codificacion_b: list[VectorCalidad]
) -> float:
    """Acuerdo ordinal entre dos codificadores sobre los mismos episodios.

    Aplana los vectores de doce celdas en una sola serie: el coeficiente se
    calcula sobre las celdas, no sobre el índice agregado, porque dos
    codificadores pueden coincidir en el promedio discrepando en cada celda.
    """
    if len(codificacion_a) != len(codificacion_b):
        raise ValueError("Ambos codificadores deben haber codificado los mismos episodios")
    if not codificacion_a:
        raise ValueError("No hay codificaciones para comparar")

    plana_a = [valor for vector in codificacion_a for valor in vector.como_vector()]
    plana_b = [valor for vector in codificacion_b for valor in vector.como_vector()]
    return acuerdo_ordinal(plana_a, plana_b)
