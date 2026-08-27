"""Motor de base de datos y provisión de sesiones."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cps.config import obtener_config

_config = obtener_config()

_argumentos_conexion = (
    {"check_same_thread": False} if _config.url_base_datos.startswith("sqlite") else {}
)

motor = create_engine(_config.url_base_datos, connect_args=_argumentos_conexion, future=True)

FabricaSesion = sessionmaker(bind=motor, autocommit=False, autoflush=False, future=True)


@event.listens_for(Engine, "connect")
def _activar_claves_foraneas(conexion, _registro) -> None:
    """SQLite ignora las claves foráneas salvo que se las habilite por conexión.

    Sin esto, las restricciones del esquema serían decorativas y se podrían
    insertar episodios apuntando a instancias inexistentes.
    """
    if _config.url_base_datos.startswith("sqlite"):
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    sesion = FabricaSesion()
    try:
        yield sesion
    finally:
        sesion.close()


@contextmanager
def sesion_de_trabajo() -> Iterator[Session]:
    """Sesión transaccional para scripts y CLI, con commit y rollback."""
    sesion = FabricaSesion()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
