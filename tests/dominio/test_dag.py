"""Tests de la estructura de la resolución canónica."""

from __future__ import annotations

import pytest

from cps.dominio.dag import ErrorDeEstructura, EstructuraSolucion, Lado, Paso


def _estructura(*pasos: Paso, final: str | None = None) -> EstructuraSolucion:
    return EstructuraSolucion(pasos=pasos, paso_final=final or pasos[-1].id)


# Una instancia bien formada: cada lado aporta una restricción, el cierre exige
# ambas y hay ida y vuelta entre los dos lados.
ESTRUCTURA_GENUINA = _estructura(
    Paso("p0", "Plantear la incógnita", Lado.PUBLICO),
    Paso("pa1", "Traza y determinante acotan el espectro", Lado.A, ("p0",)),
    Paso("pb1", "Hay exactamente dos valores propios distintos", Lado.B, ("p0",)),
    Paso("pc1", "Partir en casos combinando ambas restricciones", Lado.CONJUNTO, ("pa1", "pb1")),
    Paso("pa2", "Descartar un caso con el determinante", Lado.A, ("pc1",)),
    Paso("pf", "Escribir el polinomio característico", Lado.CONJUNTO, ("pa2",)),
)


class TestValidacion:
    def test_rechaza_identificadores_duplicados(self) -> None:
        with pytest.raises(ErrorDeEstructura, match="duplicado"):
            _estructura(
                Paso("x", "uno", Lado.PUBLICO),
                Paso("x", "otro", Lado.A),
            )

    def test_rechaza_dependencia_inexistente(self) -> None:
        with pytest.raises(ErrorDeEstructura, match="no existe"):
            _estructura(Paso("x", "uno", Lado.A, ("fantasma",)))

    def test_rechaza_paso_final_inexistente(self) -> None:
        with pytest.raises(ErrorDeEstructura, match="paso final"):
            EstructuraSolucion(pasos=(Paso("x", "uno", Lado.A),), paso_final="otro")

    def test_rechaza_ciclos(self) -> None:
        with pytest.raises(ErrorDeEstructura, match="ciclo"):
            EstructuraSolucion(
                pasos=(
                    Paso("a", "uno", Lado.A, ("b",)),
                    Paso("b", "dos", Lado.B, ("a",)),
                ),
                paso_final="a",
            )


class TestLadoEfectivo:
    def test_hereda_el_lado_de_las_dependencias(self) -> None:
        """Un paso 'público' que depende de uno de A requiere, de hecho, el dato de A."""
        estructura = _estructura(
            Paso("a", "dato de A", Lado.A),
            Paso("b", "consecuencia", Lado.PUBLICO, ("a",)),
        )
        assert estructura.lado_efectivo("b") is Lado.A

    def test_confluencia_de_ambos_lados_es_conjunta(self) -> None:
        """Así es como la emergencia aparece en la estructura."""
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "de B", Lado.B),
            Paso("c", "junta ambos", Lado.PUBLICO, ("a", "b")),
        )
        assert estructura.lado_efectivo("c") is Lado.CONJUNTO

    def test_paso_sin_dependencias_conserva_su_lado(self) -> None:
        assert ESTRUCTURA_GENUINA.lado_efectivo("p0") is Lado.PUBLICO
        assert ESTRUCTURA_GENUINA.lado_efectivo("pa1") is Lado.A


class TestClausura:
    def test_sin_datos_solo_alcanza_lo_publico(self) -> None:
        assert ESTRUCTURA_GENUINA.clausura(frozenset()) == {"p0"}

    def test_con_un_dato_no_alcanza_el_final(self) -> None:
        """La propiedad central: ninguno llega solo."""
        solo_a = ESTRUCTURA_GENUINA.clausura(frozenset({Lado.A}))
        solo_b = ESTRUCTURA_GENUINA.clausura(frozenset({Lado.B}))
        assert "pf" not in solo_a
        assert "pf" not in solo_b

    def test_con_ambos_datos_alcanza_todo(self) -> None:
        completa = ESTRUCTURA_GENUINA.clausura(frozenset({Lado.A, Lado.B}))
        assert completa == {p.id for p in ESTRUCTURA_GENUINA.pasos}


class TestEmergencia:
    def test_estructura_genuina_tiene_emergencia_positiva(self) -> None:
        assert ESTRUCTURA_GENUINA.emergencia() > 0.0

    def test_ramas_independientes_no_tienen_emergencia(self) -> None:
        """Si cada uno puede derivar su rama entera, no hay co-construcción."""
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "de B", Lado.B),
            final="a",
        )
        assert estructura.emergencia() == 0.0

    def test_todo_conjunto_da_emergencia_uno(self) -> None:
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "de B", Lado.B),
            Paso("c", "conjunto", Lado.CONJUNTO, ("a", "b")),
        )
        # De los 3 pasos no triviales, sólo 'c' es inalcanzable por separado.
        assert estructura.emergencia() == pytest.approx(1 / 3)

    def test_resolucion_totalmente_publica_da_cero(self) -> None:
        estructura = _estructura(
            Paso("a", "trivial", Lado.PUBLICO),
            Paso("b", "trivial", Lado.PUBLICO, ("a",)),
        )
        assert estructura.emergencia() == 0.0

    def test_siempre_en_cero_uno(self) -> None:
        assert 0.0 <= ESTRUCTURA_GENUINA.emergencia() <= 1.0


class TestRondasMinimas:
    def test_intercambio_unico_da_una_ronda(self) -> None:
        """A aporta, B cierra: una sola alternancia."""
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "B cierra con lo de A", Lado.B, ("a",)),
        )
        assert estructura.rondas_minimas() == 1

    def test_ida_y_vuelta_da_dos_rondas(self) -> None:
        estructura = _estructura(
            Paso("a1", "de A", Lado.A),
            Paso("b1", "de B usando a1", Lado.B, ("a1",)),
            Paso("a2", "de A usando b1", Lado.A, ("b1",)),
        )
        assert estructura.rondas_minimas() == 2

    def test_ramas_independientes_no_exigen_intercambio(self) -> None:
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "de B", Lado.B),
            final="a",
        )
        assert estructura.rondas_minimas() == 0

    def test_estructura_genuina_exige_al_menos_dos(self) -> None:
        assert ESTRUCTURA_GENUINA.rondas_minimas() >= 2

    def test_toma_el_camino_mas_largo_y_no_el_primero(self) -> None:
        """Es un máximo sobre caminos, no el de una rama arbitraria."""
        estructura = _estructura(
            Paso("corto", "de A", Lado.A),
            Paso("a1", "de A", Lado.A),
            Paso("b1", "de B", Lado.B, ("a1",)),
            Paso("a2", "de A", Lado.A, ("b1",)),
            Paso("fin", "cierra", Lado.CONJUNTO, ("corto", "a2")),
        )
        assert estructura.rondas_minimas() == 3


class TestAdvertenciasDeDiseno:
    def test_estructura_genuina_no_genera_advertencias(self) -> None:
        assert ESTRUCTURA_GENUINA.verificar_particion_genuina() == []

    def test_detecta_que_el_final_no_requiere_ambos(self) -> None:
        """Si una parte llega sola a la conclusión, la partición es falsa."""
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("b", "de B", Lado.B),
            Paso("fin", "cierra sólo con A", Lado.A, ("a",)),
        )
        advertencias = estructura.verificar_particion_genuina()
        assert any("sin el dato B" in a for a in advertencias)

    def test_no_marca_falsa_particion_cuando_el_cierre_hereda_un_lado(self) -> None:
        """Un paso que hereda A por dependencia sigue exigiendo ambos datos.

        El lado efectivo de ese paso satura en CONJUNTO, así que decidir por el
        lado efectivo daría un falso positivo. La clausura no se confunde.
        """
        estructura = _estructura(
            Paso("p0", "público", Lado.PUBLICO),
            Paso("b1", "valor intermedio de B", Lado.B, ("p0",)),
            Paso("a1", "A evalúa en el valor recibido", Lado.A, ("b1",)),
            Paso("fin", "combinar", Lado.CONJUNTO, ("a1",)),
        )
        advertencias = estructura.verificar_particion_genuina()
        assert not any("no es genuina" in a for a in advertencias)

    def test_detecta_intercambio_trivial(self) -> None:
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("fin", "B cierra de una", Lado.CONJUNTO, ("a",)),
        )
        advertencias = estructura.verificar_particion_genuina()
        assert any("partido en dos" in a for a in advertencias)

    def test_detecta_lado_ausente(self) -> None:
        estructura = _estructura(
            Paso("a", "de A", Lado.A),
            Paso("fin", "más de A", Lado.A, ("a",)),
        )
        advertencias = estructura.verificar_particion_genuina()
        assert any("no se declara como requisito" in a for a in advertencias)


def test_memoizacion_no_altera_resultados() -> None:
    """El cache de lado_efectivo no debe cambiar lo que se computa."""
    primera = [ESTRUCTURA_GENUINA.lado_efectivo(p.id) for p in ESTRUCTURA_GENUINA.pasos]
    segunda = [ESTRUCTURA_GENUINA.lado_efectivo(p.id) for p in ESTRUCTURA_GENUINA.pasos]
    assert primera == segunda
