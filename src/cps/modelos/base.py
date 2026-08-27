"""Base declarativa y tipos comunes del esquema.

Nota sobre fechas
-----------------
Todos los instantes se guardan como ``TIMESTAMP`` con zona horaria y se
construyen siempre en UTC. La versión anterior del sistema usaba ``DateTime``
sin zona: SQLite guardaba la cadena sin desplazamiento, el serializador la
emitía sin ``Z``, y el navegador la interpretaba como hora local, con lo cual el
historial aparecía corrido varias horas. En un instrumento de investigación eso
no es un detalle cosmético, porque las marcas temporales entran en el cálculo de
latencias y en el ordenamiento de los turnos.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

# Convención de nombres para que las migraciones generen restricciones con
# nombre estable; sin esto, alembic no puede alterarlas en SQLite.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class MarcaTemporal(TypeDecorator):
    """``DateTime`` que garantiza UTC consciente de zona en ambos sentidos.

    SQLite no preserva la zona horaria. Este decorador normaliza a UTC al
    escribir y vuelve a etiquetar como UTC al leer, de modo que el resto del
    sistema nunca ve un ``datetime`` ingenuo.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "Se intentó guardar un datetime sin zona horaria. Usá cps.modelos.base.ahora()."
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def ahora() -> datetime:
    """Instante actual en UTC, consciente de zona."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)
