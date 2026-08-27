"""Tests de la comparación entre modalidades."""

from __future__ import annotations

import pytest

from cps.dominio.equivalencia import (
    Muestra,
    confiabilidad_spearman_brown,
    corregir_por_atenuacion,
    correlacion_de_rangos,
    descomponer_divergencia,
    diferencia_estandarizada,
    episodios_para_equivalencia,
    prueba_equivalencia,
    resolucion_del_ordenamiento,
)


class TestMuestra:
    def test_calcula_media_y_desvio(self) -> None:
        m = Muestra.desde_valores([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert m.media == pytest.approx(5.0)
        assert m.desvio == pytest.approx(2.138, abs=1e-3)
        assert m.n == 8

    def test_rechaza_muestra_de_uno(self) -> None:
        with pytest.raises(ValueError):
            Muestra.desde_valores([1.0])


class TestDiferenciaEstandarizada:
    def test_medias_iguales_dan_cero(self) -> None:
        a = Muestra(media=0.5, desvio=0.1, n=30)
        b = Muestra(media=0.5, desvio=0.1, n=30)
        assert diferencia_estandarizada(a, b) == pytest.approx(0.0)

    def test_un_desvio_de_diferencia(self) -> None:
        a = Muestra(media=0.6, desvio=0.1, n=30)
        b = Muestra(media=0.5, desvio=0.1, n=30)
        assert diferencia_estandarizada(a, b) == pytest.approx(1.0)

    def test_acepta_escala_externa(self) -> None:
        """El caso de uso real: estandarizar contra el desvío de todo el banco."""
        a = Muestra(media=0.6, desvio=0.01, n=30)
        b = Muestra(media=0.5, desvio=0.01, n=30)
        # Con el desvío interno (0.01) la diferencia sería 10; con el del banco, 0.5.
        assert diferencia_estandarizada(a, b, escala=0.2) == pytest.approx(0.5)
        assert diferencia_estandarizada(a, b) == pytest.approx(10.0)


class TestPruebaEquivalencia:
    def test_declara_equivalencia_con_muestra_grande_y_medias_iguales(self) -> None:
        a = Muestra(media=0.50, desvio=0.10, n=200)
        b = Muestra(media=0.50, desvio=0.10, n=200)
        resultado = prueba_equivalencia(a, b, margen=0.5)
        assert resultado.equivalentes
        assert "Equivalentes" in resultado.conclusion

    def test_no_declara_equivalencia_con_muestra_chica(self) -> None:
        """El punto central: pocos datos no autorizan a afirmar equivalencia.

        Las medias son idénticas y una prueba de diferencia no rechazaría nada,
        pero eso no es evidencia de equivalencia.
        """
        a = Muestra(media=0.50, desvio=0.20, n=5)
        b = Muestra(media=0.50, desvio=0.20, n=5)
        resultado = prueba_equivalencia(a, b, margen=0.3)
        assert not resultado.equivalentes
        assert resultado.potencia_insuficiente
        assert "Indeterminado" in resultado.conclusion

    def test_detecta_diferencia_genuina(self) -> None:
        a = Muestra(media=0.80, desvio=0.10, n=200)
        b = Muestra(media=0.50, desvio=0.10, n=200)
        resultado = prueba_equivalencia(a, b, margen=0.5)
        assert not resultado.equivalentes
        assert not resultado.potencia_insuficiente
        assert "Diferentes" in resultado.conclusion

    def test_intervalo_contiene_la_diferencia(self) -> None:
        a = Muestra(media=0.55, desvio=0.10, n=100)
        b = Muestra(media=0.50, desvio=0.10, n=100)
        resultado = prueba_equivalencia(a, b, margen=0.5)
        assert resultado.intervalo[0] <= resultado.diferencia <= resultado.intervalo[1]

    def test_rechaza_margen_invalido(self) -> None:
        a = b = Muestra(media=0.5, desvio=0.1, n=30)
        with pytest.raises(ValueError):
            prueba_equivalencia(a, b, margen=0.0)


class TestTamanoMuestral:
    @pytest.mark.parametrize(
        ("margen", "esperado"),
        [(0.3, 191), (0.4, 108), (0.5, 69), (0.6, 48), (0.8, 27)],
    )
    def test_valores_de_referencia_del_diseno(self, margen: float, esperado: int) -> None:
        """Los números que determinan el dimensionamiento del brazo intensivo."""
        assert episodios_para_equivalencia(margen) == esperado

    def test_margen_mas_estricto_exige_mas_episodios(self) -> None:
        assert episodios_para_equivalencia(0.3) > episodios_para_equivalencia(0.6)

    def test_mas_potencia_exige_mas_episodios(self) -> None:
        assert episodios_para_equivalencia(0.5, potencia=0.95) > episodios_para_equivalencia(
            0.5, potencia=0.80
        )


class TestResolucionDelOrdenamiento:
    def test_caso_de_referencia(self) -> None:
        """Con dispersión 1.5 y margen 0.5 apenas se distinguen 1.5 estratos."""
        assert resolucion_del_ordenamiento(0.5, 1.5) == pytest.approx(1.5)

    def test_margen_mas_estricto_da_mas_resolucion(self) -> None:
        assert resolucion_del_ordenamiento(0.3, 1.5) > resolucion_del_ordenamiento(0.6, 1.5)


class TestDescomposicion:
    def test_modalidades_identicas_no_tienen_divergencia(self) -> None:
        valores = [0.2, 0.4, 0.5, 0.6, 0.8]
        d = descomponer_divergencia(valores, valores)
        assert d.pendiente == pytest.approx(1.0)
        assert d.ordenada == pytest.approx(0.0)
        assert d.total == pytest.approx(0.0, abs=1e-12)

    def test_desplazamiento_constante_es_sesgo_puro(self) -> None:
        """Una modalidad uniformemente más colaborativa: corregible por traslación."""
        base = [0.2, 0.4, 0.5, 0.6, 0.8]
        desplazado = [v + 0.1 for v in base]
        d = descomponer_divergencia(desplazado, base)
        assert d.pendiente == pytest.approx(1.0)
        assert d.sesgo_sistematico == pytest.approx(0.01)
        assert d.distorsion_escala == pytest.approx(0.0, abs=1e-12)
        assert d.idiosincratico == pytest.approx(0.0, abs=1e-12)
        assert d.preserva_orden

    def test_compresion_de_rango_es_distorsion_de_escala(self) -> None:
        """La modalidad artificial discrimina menos entre instancias."""
        base = [0.2, 0.4, 0.5, 0.6, 0.8]
        media = sum(base) / len(base)
        comprimido = [media + 0.5 * (v - media) for v in base]
        d = descomponer_divergencia(comprimido, base)
        assert d.pendiente == pytest.approx(0.5)
        assert d.distorsion_escala > 0.0
        assert d.idiosincratico == pytest.approx(0.0, abs=1e-12)
        assert d.preserva_orden, "comprimir no invierte el orden"

    def test_ruido_es_idiosincratico(self) -> None:
        base = [0.2, 0.4, 0.5, 0.6, 0.8]
        ruidoso = [0.25, 0.35, 0.55, 0.55, 0.85]
        d = descomponer_divergencia(ruidoso, base)
        assert d.idiosincratico > 0.0
        assert d.proporcion_irreducible > 0.0

    def test_los_tres_terminos_suman_el_total(self) -> None:
        d = descomponer_divergencia([0.3, 0.5, 0.4, 0.7, 0.6], [0.2, 0.4, 0.5, 0.6, 0.8])
        assert d.total == pytest.approx(
            d.sesgo_sistematico + d.distorsion_escala + d.idiosincratico
        )

    def test_rechaza_series_sin_dispersion(self) -> None:
        with pytest.raises(ValueError, match="no tienen dispersión"):
            descomponer_divergencia([0.1, 0.2, 0.3], [0.5, 0.5, 0.5])

    def test_rechaza_series_demasiado_cortas(self) -> None:
        with pytest.raises(ValueError, match="al menos 3"):
            descomponer_divergencia([0.1, 0.2], [0.3, 0.4])


class TestCorrelacionDeRangos:
    def test_orden_identico_da_uno(self) -> None:
        assert correlacion_de_rangos([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_orden_invertido_da_menos_uno(self) -> None:
        assert correlacion_de_rangos([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)

    def test_es_insensible_a_transformaciones_monotonas(self) -> None:
        """La compatibilidad relativa no exige que coincidan los niveles."""
        base = [0.2, 0.4, 0.5, 0.8]
        comprimido = [0.45, 0.5, 0.52, 0.6]
        assert correlacion_de_rangos(base, comprimido) == pytest.approx(1.0)

    def test_promedia_los_empates(self) -> None:
        resultado = correlacion_de_rangos([1, 2, 2, 3], [1, 2, 2, 3])
        assert resultado == pytest.approx(1.0)


class TestConfiabilidad:
    def test_valor_de_referencia_del_brazo_extensivo(self) -> None:
        """8 episodios por instancia con ICC 0.30 dan 0.77."""
        assert confiabilidad_spearman_brown(0.30, 8) == pytest.approx(0.774, abs=1e-3)

    def test_crece_con_mas_episodios(self) -> None:
        assert confiabilidad_spearman_brown(0.3, 20) > confiabilidad_spearman_brown(0.3, 4)

    def test_un_solo_episodio_devuelve_el_icc(self) -> None:
        assert confiabilidad_spearman_brown(0.3, 1) == pytest.approx(0.3)

    def test_correccion_por_atenuacion_aumenta_la_correlacion(self) -> None:
        observada = 0.5
        corregida = corregir_por_atenuacion(observada, 0.8, 0.8)
        assert corregida > observada
        assert corregida == pytest.approx(0.625)

    def test_confiabilidad_perfecta_no_corrige(self) -> None:
        assert corregir_por_atenuacion(0.5, 1.0, 1.0) == pytest.approx(0.5)

    def test_rechaza_confiabilidad_invalida(self) -> None:
        with pytest.raises(ValueError):
            corregir_por_atenuacion(0.5, 0.0, 0.8)
