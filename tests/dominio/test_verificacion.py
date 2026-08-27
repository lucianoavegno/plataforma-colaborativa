"""Tests de la verificación simbólica de respuestas.

El caso que estos tests protegen es el que motivó el módulo: que la corrección
no dependa de que el participante declare haber acertado.
"""

from __future__ import annotations

import pytest

from cps.dominio.verificacion import (
    TipoRespuesta,
    Veredicto,
    extraer_respuesta_final,
    verificar,
)


class TestExtraccion:
    def test_extrae_lo_que_sigue_al_marcador(self) -> None:
        texto = "Combinando ambos datos:\n\n[RESUELTO] x = 9"
        assert extraer_respuesta_final(texto) == "x = 9"

    def test_devuelve_none_sin_marcador(self) -> None:
        assert extraer_respuesta_final("Todavía me falta tu dato.") is None

    def test_devuelve_none_con_marcador_vacio(self) -> None:
        assert extraer_respuesta_final("blah\n\n[RESUELTO]   ") is None

    def test_corta_en_el_parrafo(self) -> None:
        texto = "[RESUELTO] 42\n\nAvisame si querés que lo verifique."
        assert extraer_respuesta_final(texto) == "42"

    def test_es_insensible_a_mayusculas(self) -> None:
        assert extraer_respuesta_final("[resuelto] 7") == "7"


class TestEquivalenciaSimbolica:
    @pytest.mark.parametrize(
        ("respuesta", "clave"),
        [
            ("9", "9"),
            ("1/2", "0.5"),
            (r"\frac{1}{2}", "0.5"),
            ("x^2 - 1", "(x-1)*(x+1)"),
            (r"\lambda^3 - 7\lambda^2 + 16\lambda - 12", "lambda**3-7*lambda**2+16*lambda-12"),
            ("$9$", "9"),
            (r"\boxed{9}", "9"),
            ("x = 9", "9"),
            ("9.", "9"),
            (r"\sqrt{4}", "2"),
        ],
    )
    def test_reconoce_formas_equivalentes(self, respuesta: str, clave: str) -> None:
        """Coincidencia textual fallaría en casi todos estos casos."""
        assert verificar(respuesta, clave).es_correcto

    @pytest.mark.parametrize(
        ("respuesta", "clave"),
        [("9", "10"), ("x^2 - 1", "x^2 + 1"), ("1/2", "1/3")],
    )
    def test_rechaza_respuestas_distintas(self, respuesta: str, clave: str) -> None:
        resultado = verificar(respuesta, clave)
        assert resultado.veredicto is Veredicto.INCORRECTO

    def test_registra_la_forma_normalizada(self) -> None:
        """Para poder auditar después qué se comparó contra qué."""
        resultado = verificar("(x-1)*(x+1)", "x^2-1")
        assert resultado.es_correcto
        assert resultado.forma_normalizada is not None


class TestVeredictosNoBinarios:
    def test_sin_respuesta_no_es_incorrecto(self) -> None:
        """Un episodio sin respuesta es dato faltante, no un error del sujeto."""
        resultado = verificar(None, "9")
        assert resultado.veredicto is Veredicto.SIN_RESPUESTA
        assert resultado.es_dato_faltante
        assert not resultado.es_correcto

    def test_cadena_vacia_es_sin_respuesta(self) -> None:
        assert verificar("   ", "9").veredicto is Veredicto.SIN_RESPUESTA

    def test_respuesta_ininteligible_es_dato_faltante(self) -> None:
        """Un fallo de parseo es del instrumento, no del participante."""
        resultado = verificar("no sé, algo con matrices ((", "9")
        assert resultado.es_dato_faltante
        assert not resultado.es_correcto

    def test_clave_invalida_es_error_del_banco(self) -> None:
        """Si la clave canónica no parsea, el problema es de la instancia."""
        with pytest.raises(ValueError, match="clave canónica"):
            verificar("9", "))(( no es una expresión")


class TestColecciones:
    def test_conjunto_ignora_el_orden(self) -> None:
        assert verificar("{3, 2, 2}", "{2, 2, 3}", TipoRespuesta.CONJUNTO).es_correcto

    def test_conjunto_respeta_multiplicidad(self) -> None:
        resultado = verificar("{2, 3}", "{2, 2, 3}", TipoRespuesta.CONJUNTO)
        assert resultado.veredicto is Veredicto.INCORRECTO

    def test_tupla_respeta_el_orden(self) -> None:
        assert verificar("(1, 2)", "(1, 2)", TipoRespuesta.TUPLA).es_correcto
        assert verificar("(2, 1)", "(1, 2)", TipoRespuesta.TUPLA).veredicto is Veredicto.INCORRECTO

    def test_conjunto_con_equivalencia_simbolica_por_elemento(self) -> None:
        assert verificar("{1/2, 3}", "{0.5, 3}", TipoRespuesta.CONJUNTO).es_correcto


class TestTexto:
    def test_normaliza_espacios_y_mayusculas(self) -> None:
        assert verificar("  Es DIAGONALIZABLE ", "es diagonalizable", TipoRespuesta.TEXTO).es_correcto

    def test_distingue_textos_distintos(self) -> None:
        resultado = verificar("no es diagonalizable", "es diagonalizable", TipoRespuesta.TEXTO)
        assert resultado.veredicto is Veredicto.INCORRECTO


def test_el_marcador_solo_no_alcanza_para_acertar() -> None:
    """La propiedad central: escribir [RESUELTO] no vuelve correcta una respuesta.

    Es exactamente el agujero que tenía la versión anterior del sistema, donde
    la presencia del token marcaba la sesión como resuelta.
    """
    texto = "[RESUELTO] la respuesta es 5"
    extraida = extraer_respuesta_final(texto)
    assert extraida is not None
    assert not verificar(extraida, "9").es_correcto
