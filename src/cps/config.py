"""Configuración del sistema, resuelta desde variables de entorno.

Todo parámetro que pueda alterar un resultado experimental se declara acá y se
registra en la exportación. Un experimento cuya configuración no queda asentada
no es reproducible, y en ese caso los números que produce no significan nada
fuera de la corrida que los generó.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Esfuerzo = Literal["low", "medium", "high", "xhigh", "max"]


class Configuracion(BaseSettings):
    """Parámetros del sistema. Se leen de ``.env`` y del entorno."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- persistencia ---------------------------------------------------------

    url_base_datos: str = "sqlite:///./plataforma.db"

    # -- seguridad ------------------------------------------------------------

    clave_secreta: str = Field(
        default="desarrollo-cambiar-en-produccion",
        description="Clave de firma de los tokens de sesión.",
    )
    algoritmo_jwt: str = "HS256"
    minutos_expiracion_token: int = Field(default=10080, ge=5)

    # -- modelos --------------------------------------------------------------

    anthropic_api_key: str | None = None

    modelo_participante: str = Field(
        default="claude-opus-5",
        description="Modelo que juega el rol de participante en los episodios.",
    )
    modelo_solver: str = Field(
        default="claude-opus-5",
        description=(
            "Solver de referencia para estimar la función de competencia. "
            "Define la escala de todos los indicadores de diseño, así que "
            "cambiarlo invalida las mediciones previas."
        ),
    )
    modelos_juez: list[str] = Field(
        default_factory=lambda: ["claude-opus-5", "claude-sonnet-5"],
        description=(
            "Jueces de codificación. Deben ser de familias distintas entre sí y "
            "distintas del modelo participante, para no premiar el propio estilo."
        ),
    )

    esfuerzo_participante: Esfuerzo = "medium"
    esfuerzo_solver: Esfuerzo = "high"
    esfuerzo_juez: Esfuerzo = "medium"

    temperatura_solver: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens_respuesta: int = Field(default=4096, ge=256)

    # -- protocolo experimental ----------------------------------------------

    ensayos_por_celda: int = Field(
        default=30,
        ge=5,
        description=(
            "N por celda de información al estimar la competencia. Con 30 se "
            "certifica v <= 0.095 ante cero aciertos; con 60, v <= 0.049."
        ),
    )
    max_turnos_episodio: int = Field(default=24, ge=2)
    turnos_por_tanda: int = Field(default=4, ge=1, le=12)

    semilla_aleatorizacion: int = Field(
        default=20260818,
        description=(
            "Semilla del generador que asigna condiciones y roles. Fijarla es "
            "lo que permite reconstruir la asignación a partir del registro."
        ),
    )

    # -- interfaz -------------------------------------------------------------

    origenes_cors: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("modelos_juez", "origenes_cors", mode="before")
    @classmethod
    def _admitir_lista_separada_por_comas(cls, valor: object) -> object:
        """Permite declarar listas como ``a,b,c`` en el archivo ``.env``."""
        if isinstance(valor, str):
            return [parte.strip() for parte in valor.split(",") if parte.strip()]
        return valor

    @field_validator("clave_secreta")
    @classmethod
    def _exigir_clave_no_trivial(cls, valor: str) -> str:
        if len(valor) < 16:
            raise ValueError("La clave secreta debe tener al menos 16 caracteres")
        return valor

    # -- derivados ------------------------------------------------------------

    @property
    def modelos_reales_disponibles(self) -> bool:
        """Sin credencial, el sistema corre con un motor simulado y determinista.

        El modo simulado sirve para desarrollar y para probar el circuito
        completo, pero los episodios que produce quedan marcados como tales y no
        deben mezclarse con datos experimentales.
        """
        return bool(self.anthropic_api_key)

    def huella_experimental(self) -> str:
        """Hash de los parámetros que afectan un resultado.

        Se guarda con cada medición. Si dos corridas tienen huellas distintas,
        no son comparables aunque hayan usado las mismas instancias, y la
        exportación lo deja explícito en lugar de que haya que deducirlo.
        """
        relevantes = {
            "modelo_participante": self.modelo_participante,
            "modelo_solver": self.modelo_solver,
            "modelos_juez": sorted(self.modelos_juez),
            "esfuerzo_participante": self.esfuerzo_participante,
            "esfuerzo_solver": self.esfuerzo_solver,
            "esfuerzo_juez": self.esfuerzo_juez,
            "temperatura_solver": self.temperatura_solver,
            "ensayos_por_celda": self.ensayos_por_celda,
            "max_turnos_episodio": self.max_turnos_episodio,
            "semilla_aleatorizacion": self.semilla_aleatorizacion,
            "simulado": not self.modelos_reales_disponibles,
        }
        serializado = json.dumps(relevantes, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serializado.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def obtener_config() -> Configuracion:
    """Instancia única de la configuración.

    Se cachea para que la huella experimental sea estable dentro de un proceso.
    Los tests que necesiten otra configuración deben limpiar el cache
    explícitamente con ``obtener_config.cache_clear()``.
    """
    return Configuracion()
