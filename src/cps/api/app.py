"""Aplicación FastAPI del instrumento."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cps.agentes.motor import obtener_motor
from cps.agentes.protocolo import VERSION_PROTOCOLO
from cps.api import esquemas
from cps.api.rutas import autenticacion, catalogo, episodios, investigacion
from cps.config import obtener_config
from cps.modelos.entidades import Modalidad

DESCRIPCION = """\
Instrumento experimental para el estudio de la resolución colaborativa de
problemas con partición de información.

Cada instancia reparte entre dos participantes datos complementarios tales que
ninguno alcanza la solución por separado. La misma instancia se resuelve en dos
modalidades comparables: dos agentes artificiales dialogando entre sí, o un
agente y un estudiante.

El esquema de la base no crea tablas al arrancar: las migraciones se aplican de
forma explícita con `alembic upgrade head`, para que el estado del esquema sea
siempre deliberado y reproducible.
"""


def crear_app() -> FastAPI:
    config = obtener_config()

    app = FastAPI(
        title="Plataforma CPS · Instrumento experimental",
        description=DESCRIPCION,
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origenes_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(autenticacion.router)
    app.include_router(catalogo.router)
    app.include_router(episodios.router)
    app.include_router(investigacion.router)

    @app.get("/api/estado", response_model=esquemas.EstadoSistema, tags=["estado"])
    def estado() -> esquemas.EstadoSistema:
        """Estado del instrumento.

        Expone la huella experimental para que quien recolecte datos pueda
        verificar, antes de empezar, que la configuración es la que espera.
        """
        motor = obtener_motor()
        return esquemas.EstadoSistema(
            version_protocolo=VERSION_PROTOCOLO,
            huella_experimental=config.huella_experimental(),
            modelos_simulados=motor.simulado,
            motivo_simulacion=motor.motivo_simulacion,
            modalidades=[m.value for m in Modalidad],
        )

    return app


app = crear_app()
