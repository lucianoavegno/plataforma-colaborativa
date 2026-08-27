"""Catálogo de instancias: lo que se puede ver sin abrir un episodio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from cps.api import esquemas
from cps.api.seguridad import cuenta_actual, investigador_actual
from cps.config import obtener_config
from cps.db import obtener_sesion
from cps.dominio.areas import AREAS, nombre_area
from cps.dominio.dag import EstructuraSolucion
from cps.dominio.indicadores import nivel_colaboratividad
from cps.modelos.entidades import Cuenta, Episodio, Instancia, MedicionDiseno, Modalidad
from cps.servicios.banco import cargar_estructura, hash_instancia

router = APIRouter(prefix="/api", tags=["catálogo"])


def _perfil_salida(medicion: MedicionDiseno | None) -> esquemas.PerfilDisenoSalida | None:
    if medicion is None:
        return None
    return esquemas.PerfilDisenoSalida(
        interdependencia=medicion.interdependencia,
        balance_carga=medicion.balance_carga,
        emergencia=medicion.emergencia,
        rondas_minimas=medicion.rondas_minimas,
        dificultad=medicion.dificultad,
        nivel=nivel_colaboratividad(medicion.interdependencia),
        monotonia_violada=medicion.monotonia_violada,
        calculada_en=medicion.calculada_en,
    )


def _medicion_vigente(instancia: Instancia, huella: str) -> MedicionDiseno | None:
    """Medición correspondiente a la huella experimental actual.

    Si el solver de referencia cambió, las mediciones previas siguen guardadas
    pero no se muestran como si describieran la configuración vigente.
    """
    for medicion in instancia.mediciones:
        if medicion.huella_experimental == huella:
            return medicion
    return None


def _resumen(instancia: Instancia, huella: str) -> esquemas.InstanciaResumen:
    return esquemas.InstanciaResumen(
        id=instancia.id,
        codigo=instancia.codigo,
        version=instancia.version,
        titulo=instancia.titulo,
        area=instancia.area,
        area_nombre=nombre_area(instancia.area),
        subtema=instancia.subtema,
        dificultad_declarada=instancia.dificultad_declarada,
        perfil=_perfil_salida(_medicion_vigente(instancia, huella)),
    )


@router.get("/areas", response_model=list[esquemas.AreaSalida])
def listar_areas(sesion: Session = Depends(obtener_sesion)) -> list[esquemas.AreaSalida]:
    conteos = dict(
        sesion.execute(
            select(Instancia.area, func.count(Instancia.id))
            .where(Instancia.activa.is_(True))
            .group_by(Instancia.area)
        ).all()
    )
    return [
        esquemas.AreaSalida(clave=clave, nombre=nombre, cantidad_instancias=conteos.get(clave, 0))
        for clave, nombre in AREAS.items()
    ]


@router.get("/rubrica")
def obtener_rubrica() -> dict:
    """La matriz de doce celdas con la que se codifica la calidad del proceso."""
    from cps.dominio.rubrica import CELDAS, DESCRIPCIONES, NivelCelda

    return {
        "celdas": [
            {
                "codigo": celda.codigo,
                "proceso": celda.proceso.value,
                "competencia": celda.competencia.value,
                "descripcion": DESCRIPCIONES[celda.codigo],
            }
            for celda in CELDAS
        ],
        "niveles": [
            {"valor": int(nivel), "nombre": nivel.name.lower()} for nivel in NivelCelda
        ],
    }


@router.get("/instancias", response_model=list[esquemas.InstanciaResumen])
def listar_instancias(
    sesion: Session = Depends(obtener_sesion),
    area: str | None = None,
    q: str | None = None,
    dificultad: int | None = Query(None, ge=1, le=5),
    interdependencia_minima: float | None = Query(None, ge=0.0, le=1.0),
    solo_calibradas: bool = False,
) -> list[esquemas.InstanciaResumen]:
    """Catálogo filtrable. Nunca devuelve datos privados ni resoluciones."""
    huella = obtener_config().huella_experimental()

    consulta = (
        select(Instancia)
        .options(selectinload(Instancia.mediciones))
        .where(Instancia.activa.is_(True))
    )

    if area:
        if area not in AREAS:
            raise HTTPException(status_code=400, detail=f"Área desconocida: {area}")
        consulta = consulta.where(Instancia.area == area)
    if dificultad:
        consulta = consulta.where(Instancia.dificultad_declarada == dificultad)
    if q:
        patron = f"%{q}%"
        consulta = consulta.where(
            Instancia.titulo.ilike(patron) | Instancia.enunciado_publico.ilike(patron)
        )

    instancias = sesion.scalars(consulta.order_by(Instancia.area, Instancia.codigo)).all()

    resultados = []
    for instancia in instancias:
        medicion = _medicion_vigente(instancia, huella)
        if solo_calibradas and medicion is None:
            continue
        if interdependencia_minima is not None and (
            medicion is None or medicion.interdependencia < interdependencia_minima
        ):
            continue
        resultados.append(_resumen(instancia, huella))
    return resultados


def _obtener_instancia(sesion: Session, instancia_id: int) -> Instancia:
    instancia = sesion.get(Instancia, instancia_id)
    if instancia is None or not instancia.activa:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")
    return instancia


@router.get("/instancias/{instancia_id}", response_model=esquemas.InstanciaDetalle)
def obtener_instancia(
    instancia_id: int, sesion: Session = Depends(obtener_sesion)
) -> esquemas.InstanciaDetalle:
    instancia = _obtener_instancia(sesion, instancia_id)
    huella = obtener_config().huella_experimental()
    return esquemas.InstanciaDetalle(
        **_resumen(instancia, huella).model_dump(),
        enunciado_publico=instancia.enunciado_publico,
    )


@router.get("/instancias/{instancia_id}/resolucion", response_model=esquemas.ResolucionSalida)
def obtener_resolucion(
    instancia_id: int,
    sesion: Session = Depends(obtener_sesion),
    cuenta: Cuenta = Depends(cuenta_actual),
) -> esquemas.ResolucionSalida:
    """Devuelve la resolución completa y registra la consulta.

    El registro no es auditoría burocrática: quien vio la resolución de una
    instancia ya no puede producir episodios válidos sobre ella, y el análisis
    necesita poder excluirlos.
    """
    from cps.modelos.entidades import EstadoEpisodio

    instancia = _obtener_instancia(sesion, instancia_id)
    config = obtener_config()

    sesion.add(
        Episodio(
            cuenta_id=cuenta.id,
            instancia_id=instancia.id,
            modalidad=Modalidad.RESOLUCION_DIRECTA,
            modelo_participante="-",
            esfuerzo_participante="-",
            huella_experimental=config.huella_experimental(),
            semilla=0,
            estado=EstadoEpisodio.FINALIZADO,
            turnos_usados=0,
        )
    )
    sesion.commit()

    return esquemas.ResolucionSalida(
        instancia_id=instancia.id,
        enunciado_publico=instancia.enunciado_publico,
        dato_a=instancia.dato_a,
        dato_b=instancia.dato_b,
        resolucion_latex=instancia.resolucion_latex,
        respuesta_canonica=instancia.respuesta_canonica,
    )


@router.post("/instancias", response_model=esquemas.InstanciaDetalle, status_code=201)
def crear_instancia(
    datos: esquemas.InstanciaCrear,
    sesion: Session = Depends(obtener_sesion),
    _: Cuenta = Depends(investigador_actual),
) -> esquemas.InstanciaDetalle:
    """Alta de instancia. Restringido a investigadores.

    Valida la estructura de la solución antes de aceptar: un DAG mal anotado
    produciría indicadores silenciosamente equivocados.
    """
    if datos.area not in AREAS:
        raise HTTPException(status_code=400, detail=f"Área desconocida: {datos.area}")

    existente = sesion.scalar(select(Instancia).where(Instancia.codigo == datos.codigo))
    version = (existente.version + 1) if existente else 1
    if existente:
        existente.activa = False

    if datos.estructura_solucion:
        try:
            cargar_estructura(datos.estructura_solucion)
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=422, detail=f"Estructura de solución inválida: {exc}"
            ) from exc
        # Las advertencias no bloquean el alta: excluir una instancia del banco
        # es decisión del investigador y no del sistema. Quedan disponibles en
        # GET /api/instancias/{id}/estructura.

    instancia = Instancia(
        codigo=datos.codigo,
        version=version,
        hash_contenido=hash_instancia(
            datos.enunciado_publico, datos.dato_a, datos.dato_b, datos.respuesta_canonica
        ),
        titulo=datos.titulo,
        area=datos.area,
        subtema=datos.subtema,
        dificultad_declarada=datos.dificultad_declarada,
        enunciado_publico=datos.enunciado_publico,
        dato_a=datos.dato_a,
        dato_b=datos.dato_b,
        respuesta_canonica=datos.respuesta_canonica,
        tipo_respuesta=datos.tipo_respuesta,
        resolucion_latex=datos.resolucion_latex,
        estructura_solucion=datos.estructura_solucion,
    )
    sesion.add(instancia)
    sesion.commit()
    sesion.refresh(instancia)

    huella = obtener_config().huella_experimental()
    return esquemas.InstanciaDetalle(
        **_resumen(instancia, huella).model_dump(),
        enunciado_publico=instancia.enunciado_publico,
    )


@router.get("/instancias/{instancia_id}/estructura")
def obtener_estructura(
    instancia_id: int,
    sesion: Session = Depends(obtener_sesion),
    _: Cuenta = Depends(investigador_actual),
) -> dict:
    """DAG anotado con sus indicadores derivados. Sólo para investigadores.

    La estructura revela cómo se combinan los datos, así que exponerla al
    catálogo público filtraría información sobre la partición.
    """
    instancia = _obtener_instancia(sesion, instancia_id)
    if not instancia.estructura_solucion:
        raise HTTPException(status_code=404, detail="Esta instancia no tiene DAG anotado")

    estructura: EstructuraSolucion = cargar_estructura(instancia.estructura_solucion)
    return {
        "pasos": [
            {
                "id": paso.id,
                "enunciado": paso.enunciado,
                "lado_declarado": paso.lado.value,
                "lado_efectivo": estructura.lado_efectivo(paso.id).value,
                "lado_ejecutor": estructura.lado_ejecutor(paso.id).value,
                "depende_de": list(paso.depende_de),
            }
            for paso in estructura.pasos
        ],
        "paso_final": estructura.paso_final,
        "emergencia": estructura.emergencia(),
        "rondas_minimas": estructura.rondas_minimas(),
        "advertencias": estructura.verificar_particion_genuina(),
    }
