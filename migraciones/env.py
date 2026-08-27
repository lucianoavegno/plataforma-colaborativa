"""Entorno de Alembic.

La URL de la base y los metadatos se toman del propio paquete, de modo que no
haya dos fuentes de verdad sobre a qué base apuntan las migraciones.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from cps.config import obtener_config
from cps.modelos import Base
from cps.modelos.base import MarcaTemporal

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", obtener_config().url_base_datos)

target_metadata = Base.metadata


def render_item(tipo_objeto, objeto, autogen_context):
    """Renderiza los tipos personalizados como su tipo de base.

    ``MarcaTemporal`` es un decorador de aplicación: normaliza a UTC al escribir
    y al leer, pero en la base no es más que un TIMESTAMP con zona. Emitirlo así
    evita que las migraciones dependan de importar el paquete, que es lo que las
    volvería frágiles ante una refactorización de los modelos.
    """
    if tipo_objeto == "type" and isinstance(objeto, MarcaTemporal):
        autogen_context.imports.add("import sqlalchemy as sa")
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        # SQLite no soporta ALTER en columnas: el modo batch reconstruye la
        # tabla, que es la única forma de migrar el esquema sin perder datos.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectable.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            render_as_batch=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
