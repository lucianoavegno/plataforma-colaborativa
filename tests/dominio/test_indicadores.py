"""Tests de los indicadores del perfil de diseño.

Los marcados con ``@pytest.mark.propiedad`` verifican propiedades formales
enunciadas en el marco teórico: no comprueban un caso, comprueban que la
implementación satisface el enunciado sobre un espacio de entradas.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cps.dominio.indicadores import (
    Competencia,
    PerfilDiseno,
    cota_superior_sin_exitos,
    intervalo_wilson,
    nivel_colaboratividad,
)

# Cuatro proporciones ordenadas que respetan la monotonía informacional y dejan
# margen suficiente para que la instancia no sea degenerada.
competencias_monotonas = st.tuples(
    st.floats(0.0, 0.2), st.floats(0.0, 0.6), st.floats(0.0, 0.6), st.floats(0.7, 1.0)
).map(
    lambda t: Competencia(
        vacia=min(t[0], t[3]),
        solo_a=max(min(t[1], t[3]), min(t[0], t[3])),
        solo_b=max(min(t[2], t[3]), min(t[0], t[3])),
        ambos=t[3],
        ensayos_por_celda=30,
    )
)


class TestIntervaloWilson:
    def test_cubre_la_proporcion_observada(self) -> None:
        inferior, superior = intervalo_wilson(15, 30)
        assert inferior < 0.5 < superior

    def test_no_colapsa_con_cero_exitos(self) -> None:
        """El motivo por el que se usa Wilson y no Wald."""
        inferior, superior = intervalo_wilson(0, 30)
        assert inferior == 0.0
        assert superior > 0.0, "Wald daría [0, 0], que afirma certeza sin datos"

    def test_no_colapsa_con_todos_los_exitos(self) -> None:
        inferior, superior = intervalo_wilson(30, 30)
        # La cota superior vale exactamente 1 en aritmética exacta; en punto
        # flotante queda a un ULP, así que se compara con tolerancia.
        assert superior == pytest.approx(1.0)
        assert inferior < 1.0

    def test_se_angosta_al_crecer_la_muestra(self) -> None:
        chico = intervalo_wilson(5, 10)
        grande = intervalo_wilson(500, 1000)
        assert (grande[1] - grande[0]) < (chico[1] - chico[0])

    @pytest.mark.parametrize(("exitos", "ensayos"), [(-1, 10), (11, 10), (0, 0)])
    def test_rechaza_conteos_invalidos(self, exitos: int, ensayos: int) -> None:
        with pytest.raises(ValueError):
            intervalo_wilson(exitos, ensayos)

    @pytest.mark.propiedad
    @given(
        ensayos=st.integers(min_value=1, max_value=500),
        fraccion=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_siempre_dentro_de_cero_uno(self, ensayos: int, fraccion: float) -> None:
        exitos = round(fraccion * ensayos)
        inferior, superior = intervalo_wilson(exitos, ensayos)
        assert 0.0 <= inferior <= superior <= 1.0


class TestCotaSinExitos:
    def test_coincide_con_la_regla_de_tres(self) -> None:
        """La aproximación 3/n debe estar cerca de la cota exacta."""
        for n in (30, 60, 100):
            assert cota_superior_sin_exitos(n) == pytest.approx(3.0 / n, abs=0.006)

    def test_valores_de_referencia_del_diseno(self) -> None:
        """Los números que el protocolo usa para fijar N por celda."""
        assert cota_superior_sin_exitos(30) == pytest.approx(0.0950, abs=1e-4)
        assert cota_superior_sin_exitos(60) == pytest.approx(0.0487, abs=1e-4)

    def test_decrece_con_mas_ensayos(self) -> None:
        assert cota_superior_sin_exitos(100) < cota_superior_sin_exitos(30)


class TestCompetencia:
    def test_ganancia_alcanzable(self) -> None:
        c = Competencia(vacia=0.05, solo_a=0.1, solo_b=0.1, ambos=0.95, ensayos_por_celda=30)
        assert c.ganancia_alcanzable == pytest.approx(0.90)

    def test_detecta_degeneracion(self) -> None:
        imposible = Competencia(
            vacia=0.0, solo_a=0.0, solo_b=0.0, ambos=0.0, ensayos_por_celda=30
        )
        assert imposible.es_degenerada
        with pytest.raises(ValueError, match="degenerada"):
            imposible.interdependencia()

    def test_detecta_violacion_de_monotonia(self) -> None:
        c = Competencia(vacia=0.5, solo_a=0.2, solo_b=0.6, ambos=0.9, ensayos_por_celda=30)
        assert c.viola_monotonia

    def test_monotonia_respetada_no_se_marca(self) -> None:
        c = Competencia(vacia=0.1, solo_a=0.2, solo_b=0.3, ambos=0.9, ensayos_por_celda=30)
        assert not c.viola_monotonia

    @pytest.mark.parametrize("campo", ["vacia", "solo_a", "solo_b", "ambos"])
    def test_rechaza_proporciones_fuera_de_rango(self, campo: str) -> None:
        argumentos = {
            "vacia": 0.1,
            "solo_a": 0.2,
            "solo_b": 0.2,
            "ambos": 0.9,
            "ensayos_por_celda": 30,
        }
        argumentos[campo] = 1.5
        with pytest.raises(ValueError):
            Competencia(**argumentos)  # type: ignore[arg-type]


class TestInterdependencia:
    def test_particion_perfecta_da_uno(self) -> None:
        """Ningún dato aislado mejora sobre el enunciado solo."""
        c = Competencia(vacia=0.0, solo_a=0.0, solo_b=0.0, ambos=1.0, ensayos_por_celda=30)
        assert c.interdependencia() == pytest.approx(1.0)

    def test_dato_suficiente_da_cero(self) -> None:
        """Si A alcanza por sí solo, no hay interdependencia."""
        c = Competencia(vacia=0.0, solo_a=1.0, solo_b=0.0, ambos=1.0, ensayos_por_celda=30)
        assert c.interdependencia() == pytest.approx(0.0)

    def test_separa_dificultad_de_interdependencia(self) -> None:
        """El defecto que la normalización corrige.

        Una instancia imposible bajo la fórmula sin normalizar daría
        interdependencia máxima. Acá se rechaza por degenerada, y la dificultad
        se reporta como indicador aparte.
        """
        imposible = Competencia(
            vacia=0.0, solo_a=0.0, solo_b=0.0, ambos=0.02, ensayos_por_celda=30
        )
        # Sin normalizar, 1 - max(v_i) = 1.0: interdependencia "perfecta".
        assert 1.0 - max(imposible.solo_a, imposible.solo_b) == pytest.approx(1.0)
        # Normalizando, la interdependencia es alta pero la dificultad la delata.
        assert imposible.dificultad() == pytest.approx(0.98)

    @pytest.mark.propiedad
    @given(competencias_monotonas)
    def test_siempre_en_cero_uno(self, c: Competencia) -> None:
        """Proposición 3.6(i)."""
        assert 0.0 <= c.interdependencia() <= 1.0


class TestBalanceDeCarga:
    def test_aportes_iguales_dan_uno(self) -> None:
        c = Competencia(vacia=0.0, solo_a=0.3, solo_b=0.3, ambos=1.0, ensayos_por_celda=30)
        assert c.balance_carga() == pytest.approx(1.0)

    def test_asimetria_total_da_cero(self) -> None:
        """Uno de los dos es un validador pasivo."""
        c = Competencia(vacia=0.0, solo_a=1.0, solo_b=0.0, ambos=1.0, ensayos_por_celda=30)
        assert c.balance_carga() == pytest.approx(0.0)

    @pytest.mark.propiedad
    @given(competencias_monotonas)
    def test_eficiencia_de_shapley(self, c: Competencia) -> None:
        """Proposición 3.11(i): φ_a + φ_b = Δ."""
        phi_a, phi_b = c.contribuciones_shapley()
        assert phi_a + phi_b == pytest.approx(c.ganancia_alcanzable, abs=1e-9)

    @pytest.mark.propiedad
    @given(competencias_monotonas)
    def test_colapso_de_la_diferencia(self, c: Competencia) -> None:
        """Proposición 3.11(ii): φ_a - φ_b = v({a}) - v({b}).

        Es el resultado que vuelve práctico al índice: la diferencia de valores
        de Shapley se calcula con dos proporciones y no requiere entropías.
        """
        phi_a, phi_b = c.contribuciones_shapley()
        assert phi_a - phi_b == pytest.approx(c.solo_a - c.solo_b, abs=1e-9)

    @pytest.mark.propiedad
    @given(competencias_monotonas)
    def test_siempre_en_cero_uno(self, c: Competencia) -> None:
        """Corolario 3.13."""
        assert 0.0 <= c.balance_carga() <= 1.0

    def test_error_estandar_crece_al_achicarse_la_ganancia(self) -> None:
        """El término en Δ⁻⁴ de la Proposición 3.14."""
        holgada = Competencia(
            vacia=0.0, solo_a=0.4, solo_b=0.1, ambos=0.95, ensayos_por_celda=30
        )
        ajustada = Competencia(
            vacia=0.0, solo_a=0.15, solo_b=0.05, ambos=0.25, ensayos_por_celda=30
        )
        assert ajustada.error_estandar_balance() > holgada.error_estandar_balance()

    def test_error_estandar_decrece_con_mas_ensayos(self) -> None:
        base = {"vacia": 0.0, "solo_a": 0.3, "solo_b": 0.1, "ambos": 0.9}
        pocos = Competencia(**base, ensayos_por_celda=30)
        muchos = Competencia(**base, ensayos_por_celda=300)
        assert muchos.error_estandar_balance() < pocos.error_estandar_balance()
        # El error escala como 1/sqrt(N).
        assert muchos.error_estandar_balance() == pytest.approx(
            pocos.error_estandar_balance() / math.sqrt(10), rel=1e-9
        )


class TestPerfilDiseno:
    def _competencia_buena(self) -> Competencia:
        return Competencia(vacia=0.02, solo_a=0.05, solo_b=0.04, ambos=0.93, ensayos_por_celda=30)

    def test_construccion_desde_competencia(self) -> None:
        perfil = PerfilDiseno.desde_competencia(
            self._competencia_buena(), emergencia=0.6, rondas_minimas=3
        )
        assert perfil.interdependencia > 0.9
        assert perfil.rondas_minimas == 3
        assert not perfil.monotonia_violada

    def test_vector_tiene_orden_estable(self) -> None:
        perfil = PerfilDiseno.desde_competencia(
            self._competencia_buena(), emergencia=0.6, rondas_minimas=3
        )
        vector = perfil.como_vector()
        assert len(vector) == 5
        assert vector[0] == perfil.interdependencia
        assert vector[3] == float(perfil.rondas_minimas)

    def test_criterio_rechaza_pocas_rondas(self) -> None:
        """Una instancia que se resuelve con un intercambio no es colaborativa."""
        perfil = PerfilDiseno.desde_competencia(
            self._competencia_buena(), emergencia=0.6, rondas_minimas=1
        )
        assert not perfil.cumple_criterio_de_diseno()

    def test_criterio_rechaza_monotonia_violada(self) -> None:
        rara = Competencia(vacia=0.5, solo_a=0.1, solo_b=0.1, ambos=0.95, ensayos_por_celda=30)
        perfil = PerfilDiseno.desde_competencia(rara, emergencia=0.8, rondas_minimas=3)
        assert perfil.monotonia_violada
        assert not perfil.cumple_criterio_de_diseno()

    def test_criterio_acepta_instancia_bien_formada(self) -> None:
        perfil = PerfilDiseno.desde_competencia(
            self._competencia_buena(), emergencia=0.6, rondas_minimas=3
        )
        assert perfil.cumple_criterio_de_diseno()


@pytest.mark.parametrize(
    ("puntaje", "esperado"),
    [
        (0.95, "Altamente interdependiente"),
        (0.80, "Altamente interdependiente"),
        (0.65, "Interdependiente"),
        (0.45, "Parcialmente interdependiente"),
        (0.10, "Débilmente interdependiente"),
    ],
)
def test_nivel_colaboratividad(puntaje: float, esperado: str) -> None:
    assert nivel_colaboratividad(puntaje) == esperado
