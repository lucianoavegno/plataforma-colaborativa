"""Tests de la API de episodios.

Se concentran en las propiedades que protegen la validez de los datos: la
frontera entre información pública y privada, la verificación de la respuesta y
la autorización.
"""

from __future__ import annotations

import pytest


class TestFronteraDeInformacion:
    """La propiedad más importante del sistema: qué información sale y cuándo."""

    def test_el_catalogo_no_expone_datos_privados(self, cliente, instancia) -> None:
        respuesta = cliente.get(f"/api/instancias/{instancia.id}")
        assert respuesta.status_code == 200

        cuerpo = respuesta.text
        assert "x^2 - 18" not in cuerpo, "el catálogo filtró el dato A"
        assert "g(2) = 5" not in cuerpo, "el catálogo filtró el dato B"
        assert "21" not in respuesta.json().get("enunciado_publico", "")

        datos = respuesta.json()
        for campo in ("dato_a", "dato_b", "respuesta_canonica", "resolucion_latex"):
            assert campo not in datos

    def test_el_listado_no_expone_datos_privados(self, cliente, instancia) -> None:
        respuesta = cliente.get("/api/instancias")
        assert respuesta.status_code == 200
        assert "x^2 - 18" not in respuesta.text

    def test_agente_agente_no_revela_ningun_dato_al_observador(
        self, cliente, instancia, participante
    ) -> None:
        """Quien mira un episodio agente-agente no debe ver los datos privados.

        Si los viera podría anticipar el diálogo, y en la modalidad con
        estudiante eso contaminaría episodios posteriores sobre la instancia.
        """
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["dato_asignado"] is None

    def test_agente_estudiante_revela_solo_el_dato_asignado(
        self, cliente, instancia, participante
    ) -> None:
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_estudiante"},
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 201, respuesta.text
        datos = respuesta.json()

        asignado = datos["dato_asignado"]
        assert asignado is not None

        # Se entrega exactamente uno de los dos, nunca ambos.
        if datos["lado_humano"] == "a":
            assert asignado == instancia.dato_a
            assert instancia.dato_b not in respuesta.text
        else:
            assert asignado == instancia.dato_b
            assert instancia.dato_a not in respuesta.text


class TestVerificacionDeRespuesta:
    """La corrección no puede depender de lo que el participante declare."""

    def _abrir(self, cliente, instancia, participante) -> int:
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_estudiante"},
            headers=participante["cabeceras"],
        )
        return respuesta.json()["id"]

    def test_respuesta_correcta_se_registra_como_acierto(
        self, cliente, instancia, participante
    ) -> None:
        episodio_id = self._abrir(cliente, instancia, participante)
        respuesta = cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "21"},
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["acerto"] is True

    def test_acepta_formas_equivalentes(self, cliente, instancia, participante) -> None:
        episodio_id = self._abrir(cliente, instancia, participante)
        respuesta = cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "$h'(2) = 7 \\cdot 3$"},
            headers=participante["cabeceras"],
        )
        assert respuesta.json()["acerto"] is True

    def test_respuesta_incorrecta_no_se_registra_como_acierto(
        self, cliente, instancia, participante
    ) -> None:
        episodio_id = self._abrir(cliente, instancia, participante)
        respuesta = cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "15"},
            headers=participante["cabeceras"],
        )
        assert respuesta.json()["acerto"] is False
        assert respuesta.json()["veredicto"] == "incorrecto"

    def test_declararse_resuelto_no_alcanza(self, cliente, instancia, participante) -> None:
        """El agujero del sistema anterior: escribir el marcador marcaba éxito."""
        episodio_id = self._abrir(cliente, instancia, participante)
        respuesta = cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "[RESUELTO] ya está, lo resolví"},
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["acerto"] is False

    def test_no_se_puede_responder_dos_veces(
        self, cliente, instancia, participante
    ) -> None:
        episodio_id = self._abrir(cliente, instancia, participante)
        cabeceras = participante["cabeceras"]
        cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "15"},
            headers=cabeceras,
        )
        segunda = cliente.post(
            f"/api/episodios/{episodio_id}/respuesta",
            json={"respuesta": "21"},
            headers=cabeceras,
        )
        assert segunda.status_code == 400


class TestAutorizacion:
    def test_sin_token_no_se_crea_episodio(self, cliente, instancia) -> None:
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
        )
        assert respuesta.status_code == 401

    def test_un_participante_no_lee_episodios_ajenos(
        self, cliente, instancia, participante
    ) -> None:
        episodio_id = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        ).json()["id"]

        otro = cliente.post(
            "/api/auth/registro",
            json={
                "email": "otro@pruebas-cps.org",
                "nombre": "Otra persona",
                "password": "contrasena-larga",
                "acepta_consentimiento": True,
            },
        ).json()

        respuesta = cliente.get(
            f"/api/episodios/{episodio_id}",
            headers={"Authorization": f"Bearer {otro['access_token']}"},
        )
        assert respuesta.status_code == 403

    def test_un_participante_no_crea_instancias(self, cliente, participante) -> None:
        """El banco es el instrumento: alterarlo requiere rol de investigador."""
        respuesta = cliente.post(
            "/api/instancias",
            json={
                "codigo": "intruso",
                "titulo": "Instancia intrusa",
                "area": "algebra_lineal",
                "enunciado_publico": "un enunciado cualquiera",
                "dato_a": "a",
                "dato_b": "b",
                "respuesta_canonica": "1",
                "resolucion_latex": "una resolución",
            },
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 403

    def test_un_participante_no_accede_a_la_exportacion(
        self, cliente, participante
    ) -> None:
        respuesta = cliente.get(
            "/api/investigacion/exportacion.jsonl", headers=participante["cabeceras"]
        )
        assert respuesta.status_code == 403

    def test_un_participante_no_fija_la_condicion(
        self, cliente, instancia, participante
    ) -> None:
        """Fijar la condición a mano rompería la aleatorización."""
        respuesta = cliente.post(
            "/api/episodios",
            json={
                "instancia_id": instancia.id,
                "modalidad": "agente_agente",
                "condicion_divulgacion": "restringida",
            },
            headers=participante["cabeceras"],
        )
        assert respuesta.status_code == 403

    def test_el_investigador_si_accede_a_la_exportacion(
        self, cliente, investigador
    ) -> None:
        respuesta = cliente.get(
            "/api/investigacion/exportacion.jsonl", headers=investigador["cabeceras"]
        )
        assert respuesta.status_code == 200


class TestAsignacionExperimental:
    def test_la_condicion_se_asigna_y_se_registra(
        self, cliente, instancia, participante
    ) -> None:
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        )
        datos = respuesta.json()
        assert datos["condicion_divulgacion"] in ("libre", "restringida")

    def test_agente_agente_no_asigna_lado_humano(
        self, cliente, instancia, participante
    ) -> None:
        """No hay humano dentro del episodio, así que no hay rol que contrabalancear."""
        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        )
        assert respuesta.json()["lado_humano"] is None

    def test_agente_estudiante_contrabalancea_el_lado(
        self, cliente, instancia, sesion
    ) -> None:
        """A lo largo de varios episodios, ambos lados deben aparecer.

        Sin contrabalanceo, la comparación entre modalidades quedaría confundida
        con el efecto del rol, porque en agente-agente ambos roles son
        artificiales.
        """
        lados = set()
        for indice in range(6):
            cuenta = cliente.post(
                "/api/auth/registro",
                json={
                    "email": f"p{indice}@pruebas-cps.org",
                    "nombre": f"Participante {indice}",
                    "password": "contrasena-larga",
                    "acepta_consentimiento": True,
                },
            ).json()
            respuesta = cliente.post(
                "/api/episodios",
                json={"instancia_id": instancia.id, "modalidad": "agente_estudiante"},
                headers={"Authorization": f"Bearer {cuenta['access_token']}"},
            )
            lados.add(respuesta.json()["lado_humano"])

        assert lados == {"a", "b"}, f"no se contrabalanceó el rol: {lados}"

    def test_el_episodio_registra_la_huella_experimental(
        self, cliente, instancia, participante, sesion
    ) -> None:
        from cps.modelos.entidades import Episodio

        episodio_id = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        ).json()["id"]

        episodio = sesion.get(Episodio, episodio_id)
        assert episodio.huella_experimental
        assert episodio.semilla != 0
        assert episodio.simulado is True, "sin credencial, el episodio debe quedar marcado"


class TestConsentimiento:
    def test_no_se_puede_registrar_sin_aceptar(self, cliente) -> None:
        respuesta = cliente.post(
            "/api/auth/registro",
            json={
                "email": "sin-consentimiento@pruebas-cps.org",
                "nombre": "Alguien",
                "password": "contrasena-larga",
                "acepta_consentimiento": False,
            },
        )
        assert respuesta.status_code == 422

    def test_el_texto_esta_disponible_antes_de_aceptarlo(self, cliente) -> None:
        respuesta = cliente.get("/api/auth/consentimiento")
        assert respuesta.status_code == 200
        datos = respuesta.json()
        assert datos["version"]
        assert "no una persona" in datos["cuerpo"]
        assert "desvinculada" in datos["cuerpo"]

    def test_tras_retirarlo_no_se_crean_episodios(
        self, cliente, instancia, participante
    ) -> None:
        cabeceras = participante["cabeceras"]
        assert cliente.post("/api/auth/retirar-consentimiento", headers=cabeceras).status_code == 204

        respuesta = cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=cabeceras,
        )
        assert respuesta.status_code == 403


class TestSeudonimizacion:
    def test_la_exportacion_no_incluye_correos(
        self, cliente, instancia, participante, investigador
    ) -> None:
        cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        )

        respuesta = cliente.get(
            "/api/investigacion/exportacion.jsonl?incluir_simulados=true",
            headers=investigador["cabeceras"],
        )
        assert respuesta.status_code == 200
        assert "participante@pruebas-cps.org" not in respuesta.text
        assert participante["cuenta"]["seudonimo"] in respuesta.text

    def test_los_simulados_se_excluyen_por_defecto(
        self, cliente, instancia, participante, investigador
    ) -> None:
        """Un episodio sin credencial de modelo no es dato experimental."""
        cliente.post(
            "/api/episodios",
            json={"instancia_id": instancia.id, "modalidad": "agente_agente"},
            headers=participante["cabeceras"],
        )
        respuesta = cliente.get(
            "/api/investigacion/exportacion.jsonl", headers=investigador["cabeceras"]
        )
        assert respuesta.text.strip() == ""


def test_el_estado_expone_la_huella(cliente) -> None:
    respuesta = cliente.get("/api/estado")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["huella_experimental"]
    assert datos["version_protocolo"]
    assert datos["modelos_simulados"] is True


@pytest.mark.parametrize("modalidad", ["resolucion_directa"])
def test_la_resolucion_no_se_abre_como_episodio(
    cliente, instancia, participante, modalidad: str
) -> None:
    respuesta = cliente.post(
        "/api/episodios",
        json={"instancia_id": instancia.id, "modalidad": modalidad},
        headers=participante["cabeceras"],
    )
    assert respuesta.status_code == 400


def test_consultar_la_resolucion_queda_registrado(
    cliente, instancia, participante, sesion
) -> None:
    """Quien vio la resolución no puede producir episodios válidos sobre la instancia."""
    from cps.modelos.entidades import Episodio, Modalidad

    respuesta = cliente.get(
        f"/api/instancias/{instancia.id}/resolucion", headers=participante["cabeceras"]
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["dato_a"] == instancia.dato_a

    registros = (
        sesion.query(Episodio)
        .filter(Episodio.modalidad == Modalidad.RESOLUCION_DIRECTA)
        .all()
    )
    assert len(registros) == 1
