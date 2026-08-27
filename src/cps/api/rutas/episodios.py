"""Episodios: creación, avance del diálogo y cierre verificado."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cps.agentes.motor import ErrorDeModelo, MotorModelos, obtener_motor
from cps.api import esquemas
from cps.api.seguridad import cuenta_actual
from cps.config import Configuracion, obtener_config
from cps.db import obtener_sesion
from cps.dominio.areas import nombre_area
from cps.modelos.entidades import Cuenta, Episodio, Instancia, Modalidad, Rol
from cps.servicios import episodios as servicio

router = APIRouter(prefix="/api/episodios", tags=["episodios"])


def _mi_episodio(sesion: Session, episodio_id: int, cuenta: Cuenta) -> Episodio:
    """Recupera un episodio verificando la propiedad.

    Un investigador puede leer cualquier episodio; un participante, sólo los
    propios. Sin esta comprobación, conocer un identificador bastaría para leer
    el transcript de otra persona.
    """
    episodio = sesion.get(
        Episodio,
        episodio_id,
        options=[selectinload(Episodio.turnos), selectinload(Episodio.instancia)],
    )
    if episodio is None:
        raise HTTPException(status_code=404, detail="Episodio no encontrado")
    if episodio.cuenta_id != cuenta.id and cuenta.rol != Rol.INVESTIGADOR:
        raise HTTPException(status_code=403, detail="Este episodio pertenece a otra cuenta")
    return episodio


def _detalle(episodio: Episodio) -> esquemas.EpisodioDetalle:
    return esquemas.EpisodioDetalle(
        **_resumen(episodio).model_dump(),
        turnos=[esquemas.TurnoSalida.model_validate(t) for t in episodio.turnos],
        dato_asignado=servicio.dato_para_humano(episodio),
        enunciado_publico=episodio.instancia.enunciado_publico if episodio.instancia else None,
    )


def _resumen(episodio: Episodio) -> esquemas.EpisodioResumen:
    return esquemas.EpisodioResumen(
        id=episodio.id,
        instancia_id=episodio.instancia_id,
        instancia_titulo=episodio.instancia.titulo if episodio.instancia else None,
        area_nombre=nombre_area(episodio.instancia.area) if episodio.instancia else None,
        modalidad=episodio.modalidad,
        condicion_divulgacion=episodio.condicion_divulgacion,
        lado_humano=episodio.lado_humano,
        estado=episodio.estado,
        turnos_usados=episodio.turnos_usados,
        acerto=episodio.acerto,
        veredicto=episodio.veredicto,
        simulado=episodio.simulado,
        iniciado_en=episodio.iniciado_en,
        finalizado_en=episodio.finalizado_en,
    )


@router.post("", response_model=esquemas.EpisodioDetalle, status_code=201)
def crear(
    datos: esquemas.EpisodioCrear,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
    config: Configuracion = Depends(obtener_config),
    motor: MotorModelos = Depends(obtener_motor),
) -> esquemas.EpisodioDetalle:
    """Abre un episodio con su condición experimental asignada."""
    if datos.modalidad is Modalidad.RESOLUCION_DIRECTA:
        raise HTTPException(
            status_code=400,
            detail="La resolución directa se consulta en /api/instancias/{id}/resolucion",
        )

    if not any(c.vigente for c in cuenta.consentimientos):
        raise HTTPException(
            status_code=403,
            detail="No hay consentimiento vigente para esta cuenta.",
        )

    instancia = sesion.get(Instancia, datos.instancia_id)
    if instancia is None or not instancia.activa:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")

    # Fijar la condición a mano rompe la aleatorización, así que se reserva a
    # investigadores (por ejemplo, para reponer una celda faltante del diseño).
    if (
        datos.condicion_divulgacion is not None or datos.lado_humano is not None
    ) and cuenta.rol != Rol.INVESTIGADOR:
        raise HTTPException(
            status_code=403,
            detail="Fijar la condición o el lado requiere rol de investigador",
        )

    episodio = servicio.crear_episodio(
        sesion,
        cuenta=cuenta,
        instancia=instancia,
        modalidad=datos.modalidad,
        config=config,
        motor=motor,
        condicion_forzada=datos.condicion_divulgacion,
        lado_forzado=datos.lado_humano,
    )
    sesion.commit()
    sesion.refresh(episodio)
    return _detalle(episodio)


@router.get("", response_model=list[esquemas.EpisodioResumen])
def listar(
    sesion: Session = Depends(obtener_sesion), cuenta: Cuenta = Depends(cuenta_actual)
) -> list[esquemas.EpisodioResumen]:
    episodios = sesion.scalars(
        select(Episodio)
        .options(selectinload(Episodio.instancia))
        .where(Episodio.cuenta_id == cuenta.id)
        .order_by(Episodio.iniciado_en.desc())
    ).all()
    return [_resumen(e) for e in episodios]


@router.get("/{episodio_id}", response_model=esquemas.EpisodioDetalle)
def obtener(
    episodio_id: int,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
) -> esquemas.EpisodioDetalle:
    return _detalle(_mi_episodio(sesion, episodio_id, cuenta))


@router.post("/{episodio_id}/ejecutar", response_model=esquemas.EpisodioDetalle)
def ejecutar_tanda(
    episodio_id: int,
    datos: esquemas.EjecutarTanda,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
    config: Configuracion = Depends(obtener_config),
    motor: MotorModelos = Depends(obtener_motor),
) -> esquemas.EpisodioDetalle:
    """Corre una tanda de turnos entre los dos agentes."""
    episodio = _mi_episodio(sesion, episodio_id, cuenta)
    try:
        servicio.avanzar_dialogo_agentes(
            sesion, episodio, turnos=datos.turnos, motor=motor, config=config
        )
    except servicio.ErrorDeEpisodio as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorDeModelo as exc:
        # No se persiste nada: una tanda a medias produciría un transcript con
        # un hueco silencioso, que es peor que no tener la tanda.
        sesion.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    sesion.commit()
    sesion.refresh(episodio)
    return _detalle(episodio)


@router.post("/{episodio_id}/mensajes", response_model=esquemas.EpisodioDetalle)
def enviar_mensaje(
    episodio_id: int,
    datos: esquemas.MensajeEntrada,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
    config: Configuracion = Depends(obtener_config),
    motor: MotorModelos = Depends(obtener_motor),
) -> esquemas.EpisodioDetalle:
    """Registra el turno del estudiante y devuelve la respuesta del agente."""
    episodio = _mi_episodio(sesion, episodio_id, cuenta)
    if episodio.cuenta_id != cuenta.id:
        raise HTTPException(status_code=403, detail="Sólo el participante puede escribir")

    try:
        servicio.responder_a_humano(
            sesion, episodio, mensaje=datos.contenido, motor=motor, config=config
        )
    except servicio.ErrorDeEpisodio as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ErrorDeModelo as exc:
        sesion.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    sesion.commit()
    sesion.refresh(episodio)
    return _detalle(episodio)


@router.post("/{episodio_id}/respuesta", response_model=esquemas.ResultadoVerificacion)
def enviar_respuesta_final(
    episodio_id: int,
    datos: esquemas.RespuestaFinal,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
) -> esquemas.ResultadoVerificacion:
    """Cierra el episodio verificando la respuesta contra la clave canónica.

    Es la única vía por la que un episodio queda registrado como acertado. No
    existe detección de marcadores en el texto del diálogo, porque eso haría que
    la variable dependiente principal dependiera de lo que el participante
    escriba sobre sí mismo.
    """
    episodio = _mi_episodio(sesion, episodio_id, cuenta)
    try:
        veredicto, acerto, normalizada = servicio.cerrar_con_respuesta(
            sesion, episodio, respuesta=datos.respuesta
        )
    except servicio.ErrorDeEpisodio as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sesion.commit()
    return esquemas.ResultadoVerificacion(
        veredicto=veredicto,
        acerto=acerto,
        respuesta_registrada=datos.respuesta,
        forma_normalizada=normalizada,
    )


@router.post("/{episodio_id}/abandonar", response_model=esquemas.EpisodioResumen)
def abandonar(
    episodio_id: int,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
) -> esquemas.EpisodioResumen:
    """Cierra el episodio sin respuesta. Queda como dato faltante."""
    episodio = _mi_episodio(sesion, episodio_id, cuenta)
    servicio.abandonar(sesion, episodio)
    sesion.commit()
    sesion.refresh(episodio)
    return _resumen(episodio)
