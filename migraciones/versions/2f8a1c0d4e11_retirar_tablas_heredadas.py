"""Retira las tablas del esquema anterior

El esquema previo modelaba "problemas", "sesiones" y "mensajes". El actual los
reemplaza por "instancias", "episodios" y "turnos", que no son un renombre sino
un modelo distinto: separa la instancia de su medición, registra la condición
experimental y la asignación de rol, y guarda el costo por turno.

El contenido de los problemas ya se migró a los archivos de ``datos/instancias``
mediante ``scripts/migrar_banco_v0.py``. Las cuentas y sesiones del esquema
anterior no se migran a propósito: sus sesiones se marcaban como resueltas por
la presencia de un token en el texto, que el participante podía escribir por su
cuenta, así que no constituyen observaciones válidas.

La bajada recrea las tablas vacías: permite volver al esquema anterior pero no
recupera los datos, que es lo honesto para una migración destructiva.

ID de revisión: 2f8a1c0d4e11
Revisión anterior: 288fc4b9c21a
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "2f8a1c0d4e11"
down_revision = "288fc4b9c21a"
branch_labels = None
depends_on = None

# Orden de borrado: primero las que tienen claves foráneas hacia las otras.
TABLAS_HEREDADAS = (
    "mensajes",
    "sesiones",
    "analisis_colaborativos",
    "problemas",
    "usuarios",
)


def upgrade() -> None:
    conexion = op.get_bind()
    inspector = sa.inspect(conexion)
    existentes = set(inspector.get_table_names())

    for tabla in TABLAS_HEREDADAS:
        if tabla in existentes:
            op.drop_table(tabla)


def downgrade() -> None:
    """Recrea la estructura vacía del esquema anterior.

    No restaura contenido: los datos se respaldan por fuera de la migración.
    """
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("hash_password", sa.String(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "problemas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(), nullable=True),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("subtema", sa.String(), nullable=True),
        sa.Column("dificultad", sa.Integer(), nullable=True),
        sa.Column("enunciado_base", sa.Text(), nullable=False),
        sa.Column("dato_a", sa.Text(), nullable=False),
        sa.Column("dato_b", sa.Text(), nullable=False),
        sa.Column("resolucion_latex", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "analisis_colaborativos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problema_id", sa.Integer(), sa.ForeignKey("problemas.id"), nullable=False),
        sa.Column("dimensiones", sa.JSON(), nullable=True),
        sa.Column("tipos_resolucion", sa.JSON(), nullable=True),
        sa.Column("puntaje_colaborativo", sa.Float(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "sesiones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("problema_id", sa.Integer(), sa.ForeignKey("problemas.id"), nullable=False),
        sa.Column("modo", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=True),
        sa.Column("resuelto", sa.Boolean(), nullable=True),
        sa.Column("turnos", sa.Integer(), nullable=True),
        sa.Column("creada_en", sa.DateTime(), nullable=True),
        sa.Column("finalizada_en", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "mensajes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sesion_id", sa.Integer(), sa.ForeignKey("sesiones.id"), nullable=False),
        sa.Column("rol", sa.String(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )
