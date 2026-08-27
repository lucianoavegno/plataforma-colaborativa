"""Tests de la rúbrica de calidad del proceso."""

from __future__ import annotations

import pytest

from cps.dominio.rubrica import (
    CELDAS,
    CODIGO_A_CELDA,
    DESCRIPCIONES,
    NivelCelda,
    VectorCalidad,
    acuerdo_ordinal,
)


def _vector(valor: int) -> VectorCalidad:
    return VectorCalidad.desde_dict({codigo: valor for codigo in CODIGO_A_CELDA})


class TestMatriz:
    def test_tiene_doce_celdas(self) -> None:
        assert len(CELDAS) == 12

    def test_los_codigos_son_unicos(self) -> None:
        assert len({c.codigo for c in CELDAS}) == 12

    def test_toda_celda_tiene_descripcion(self) -> None:
        assert set(DESCRIPCIONES) == set(CODIGO_A_CELDA)

    def test_el_orden_es_estable(self) -> None:
        """El orden es parte del contrato de datos de la exportación."""
        assert [c.codigo for c in CELDAS] == [c.codigo for c in CELDAS]
        assert CELDAS[0].codigo == "EX-CO"


class TestVectorCalidad:
    def test_todo_ausente_da_cero(self) -> None:
        assert _vector(0).indice_calidad() == pytest.approx(0.0)

    def test_todo_emergente_da_uno(self) -> None:
        assert _vector(3).indice_calidad() == pytest.approx(1.0)

    def test_valor_intermedio(self) -> None:
        assert _vector(2).indice_calidad() == pytest.approx(24 / 36)

    def test_rechaza_celdas_faltantes(self) -> None:
        with pytest.raises(ValueError, match="Faltan celdas"):
            VectorCalidad.desde_dict({"EX-CO": 2})

    def test_rechaza_celdas_desconocidas(self) -> None:
        datos = {codigo: 1 for codigo in CODIGO_A_CELDA}
        datos["XX-YY"] = 1
        with pytest.raises(ValueError, match="desconocidas"):
            VectorCalidad.desde_dict(datos)

    def test_rechaza_puntaje_fuera_de_escala(self) -> None:
        datos = {codigo: 1 for codigo in CODIGO_A_CELDA}
        datos["EX-CO"] = 7
        with pytest.raises(ValueError, match="Puntaje inválido"):
            VectorCalidad.desde_dict(datos)

    def test_celdas_activas_cuenta_desde_funcional(self) -> None:
        """Una celda superficial no es evidencia de que la competencia se ejerció."""
        assert _vector(NivelCelda.SUPERFICIAL).celdas_activas() == 0
        assert _vector(NivelCelda.FUNCIONAL).celdas_activas() == 12

    def test_celdas_emergentes(self) -> None:
        assert _vector(NivelCelda.FUNCIONAL).celdas_emergentes() == 0
        assert _vector(NivelCelda.EMERGENTE).celdas_emergentes() == 12

    def test_vector_tiene_doce_enteros(self) -> None:
        assert len(_vector(2).como_vector()) == 12

    def test_perfiles_marginales_suman_coherente(self) -> None:
        """Los promedios por competencia y por proceso deben dar el CQI global."""
        vector = _vector(2)
        por_competencia = vector.perfil_por_competencia()
        por_proceso = vector.perfil_por_proceso()
        assert len(por_competencia) == 3
        assert len(por_proceso) == 4
        promedio_c = sum(por_competencia.values()) / 3
        promedio_p = sum(por_proceso.values()) / 4
        assert promedio_c == pytest.approx(vector.indice_calidad())
        assert promedio_p == pytest.approx(vector.indice_calidad())

    def test_perfiles_distinguen_lo_que_el_cqi_promedia(self) -> None:
        """Dos episodios con el mismo CQI pueden tener perfiles muy distintos."""
        datos_a = {c.codigo: (3 if c.codigo.startswith("EX") else 1) for c in CELDAS}
        datos_b = {c.codigo: (3 if c.codigo.startswith("MO") else 1) for c in CELDAS}
        a, b = VectorCalidad.desde_dict(datos_a), VectorCalidad.desde_dict(datos_b)
        assert a.indice_calidad() == pytest.approx(b.indice_calidad())
        assert a.perfil_por_proceso() != b.perfil_por_proceso()


class TestAcuerdoOrdinal:
    def test_acuerdo_perfecto_da_uno(self) -> None:
        codificacion = [0, 1, 2, 3, 2, 1, 0, 3]
        assert acuerdo_ordinal(codificacion, codificacion) == pytest.approx(1.0)

    def test_desacuerdo_sistematico_da_valor_bajo(self) -> None:
        a = [0, 0, 0, 0, 3, 3, 3, 3]
        b = [3, 3, 3, 3, 0, 0, 0, 0]
        assert acuerdo_ordinal(a, b) < 0.0

    def test_acuerdo_alto_supera_el_umbral_convencional(self) -> None:
        a = [0, 1, 2, 3, 1, 2, 3, 2, 1, 0]
        b = [0, 1, 2, 3, 1, 2, 2, 2, 1, 0]
        assert acuerdo_ordinal(a, b) >= 0.80

    def test_penaliza_menos_los_desacuerdos_cercanos(self) -> None:
        """Es ordinal: confundir 2 con 3 es menos grave que confundir 0 con 3."""
        base = [0, 1, 2, 3, 0, 1, 2, 3]
        cercano = [0, 1, 2, 2, 0, 1, 2, 2]
        lejano = [0, 1, 2, 0, 0, 1, 2, 0]
        assert acuerdo_ordinal(base, cercano) > acuerdo_ordinal(base, lejano)

    def test_rechaza_longitudes_distintas(self) -> None:
        with pytest.raises(ValueError, match="misma longitud"):
            acuerdo_ordinal([1, 2], [1])

    def test_rechaza_entrada_vacia(self) -> None:
        with pytest.raises(ValueError):
            acuerdo_ordinal([], [])

    def test_rechaza_valores_fuera_de_escala(self) -> None:
        with pytest.raises(ValueError, match="fuera de la escala"):
            acuerdo_ordinal([0, 9], [0, 1])

    def test_sin_variabilidad_marginal_y_sin_desacuerdo(self) -> None:
        assert acuerdo_ordinal([2, 2, 2], [2, 2, 2]) == pytest.approx(1.0)
