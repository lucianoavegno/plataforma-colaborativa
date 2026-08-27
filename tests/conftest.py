"""Fixtures compartidas de la suite.

Los tests de API corren contra una base temporal en disco, creada con las mismas
migraciones que la base real. Se usa el archivo y no memoria porque el motor
comparte conexiones entre hilos y una base en memoria por conexión no vería las
mismas tablas.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# La configuración se lee al importar, así que el entorno debe fijarse antes de
# que cualquier módulo del paquete entre en juego.
os.environ.setdefault("CLAVE_SECRETA", "clave-de-pruebas-suficientemente-larga")
os.environ.setdefault("ANTHROPIC_API_KEY", "")


@pytest.fixture(scope="session")
def ruta_base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("cps") / "pruebas.db"


@pytest.fixture(scope="session", autouse=True)
def _configurar_entorno(ruta_base: Path) -> Iterator[None]:
    os.environ["URL_BASE_DATOS"] = f"sqlite:///{ruta_base}"
    yield


@pytest.fixture(scope="session")
def motor_pruebas(_configurar_entorno: None):
    """Crea el esquema en la base temporal."""
    from cps.config import obtener_config
    from cps.db import motor
    from cps.modelos import Base

    obtener_config.cache_clear()
    Base.metadata.create_all(bind=motor)
    return motor


@pytest.fixture
def sesion(motor_pruebas) -> Iterator:
    """Sesión de base con limpieza entre tests.

    Se vacían las tablas en orden inverso de dependencia en lugar de recrear el
    esquema, que es mucho más rápido y deja el mismo estado.
    """
    from cps.db import FabricaSesion
    from cps.modelos import Base

    sesion_bd = FabricaSesion()
    try:
        yield sesion_bd
    finally:
        sesion_bd.rollback()
        for tabla in reversed(Base.metadata.sorted_tables):
            sesion_bd.execute(tabla.delete())
        sesion_bd.commit()
        sesion_bd.close()


@pytest.fixture
def cliente(sesion) -> Iterator:
    """Cliente HTTP contra la aplicación real, compartiendo la sesión del test."""
    from fastapi.testclient import TestClient

    from cps.api.app import crear_app
    from cps.db import obtener_sesion

    app = crear_app()
    app.dependency_overrides[obtener_sesion] = lambda: sesion

    with TestClient(app) as cliente_http:
        yield cliente_http

    app.dependency_overrides.clear()


@pytest.fixture
def instancia(sesion):
    """Una instancia mínima pero válida, con partición genuina."""
    from cps.modelos.entidades import Instancia
    from cps.servicios.banco import hash_instancia

    registro = Instancia(
        codigo="test-cadena",
        version=1,
        hash_contenido=hash_instancia("enunciado", "dato a", "dato b", "21"),
        titulo="Instancia de prueba",
        area="calculo_dif_int",
        subtema="Regla de la cadena",
        dificultad_declarada=3,
        enunciado_publico="Calcular $h'(2)$ con $h = f \\circ g$.",
        dato_a="Conocés $f'(x) = x^2 - 18$.",
        dato_b="Conocés $g(2) = 5$ y $g'(2) = 3$.",
        respuesta_canonica="21",
        tipo_respuesta="expresion",
        resolucion_latex="Por la regla de la cadena, $h'(2) = f'(g(2))g'(2) = 21$.",
        estructura_solucion={
            "pasos": [
                {"id": "p0", "enunciado": "regla de la cadena", "lado": "publico"},
                {"id": "b1", "enunciado": "g(2)=5", "lado": "b", "depende_de": ["p0"]},
                {"id": "b2", "enunciado": "g'(2)=3", "lado": "b", "depende_de": ["p0"]},
                {"id": "a1", "enunciado": "f'(5)=7", "lado": "a", "depende_de": ["b1"]},
                {"id": "c1", "enunciado": "producto", "lado": "conjunto", "depende_de": ["a1", "b2"]},
            ],
            "paso_final": "c1",
        },
    )
    sesion.add(registro)
    sesion.commit()
    sesion.refresh(registro)
    return registro


@pytest.fixture
def participante(cliente) -> dict:
    """Cuenta de participante registrada, con su token."""
    respuesta = cliente.post(
        "/api/auth/registro",
        json={
            "email": "participante@pruebas-cps.org",
            "nombre": "Participante de prueba",
            "password": "contrasena-larga",
            "acepta_consentimiento": True,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    return {
        "token": datos["access_token"],
        "cuenta": datos["cuenta"],
        "cabeceras": {"Authorization": f"Bearer {datos['access_token']}"},
    }


@pytest.fixture
def investigador(cliente, sesion) -> dict:
    """Cuenta con rol de investigador."""
    from cps.modelos.entidades import Cuenta, Rol

    respuesta = cliente.post(
        "/api/auth/registro",
        json={
            "email": "investigador@pruebas-cps.org",
            "nombre": "Investigadora de prueba",
            "password": "contrasena-larga",
            "acepta_consentimiento": True,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()

    cuenta = sesion.get(Cuenta, datos["cuenta"]["id"])
    cuenta.rol = Rol.INVESTIGADOR
    sesion.commit()

    return {
        "token": datos["access_token"],
        "cuenta": datos["cuenta"],
        "cabeceras": {"Authorization": f"Bearer {datos['access_token']}"},
    }
