#!/usr/bin/env python3
"""Migración del banco de la versión anterior al formato de archivos.

La versión anterior guardaba los problemas como literales dentro de un script y
carecía de dos cosas que el instrumento necesita: una respuesta canónica contra
la cual verificar, y el DAG anotado de la resolución.

Este script combina el contenido de texto ya existente (enunciados, datos y
resoluciones en LaTeX, que se leen de la base vieja) con los campos nuevos, que
se declaran acá porque exigieron resolver cada problema y anotar su estructura.

Se corre una sola vez. A partir de ahí, la fuente de verdad del banco son los
archivos de ``datos/instancias/``.

    python scripts/migrar_banco_v0.py --base plataforma.db --salida datos/instancias
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import yaml

# Campos que la versión anterior no tenía. El DAG se anotó resolviendo cada
# problema y registrando de qué dato privado depende cada paso.
CAMPOS_NUEVOS: dict[str, dict] = {
    "El polinomio característico oculto": {
        "codigo": "al-espectro-oculto",
        "respuesta_canonica": r"\lambda^3 - 7\lambda^2 + 16\lambda - 12",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "El polinomio mónico se escribe con las funciones simétricas del espectro", "lado": "publico"},
                {"id": "a1", "enunciado": "De la traza y el determinante: suma 7 y producto 12", "lado": "a", "depende_de": ["p0"]},
                {"id": "b1", "enunciado": "Hay exactamente dos valores propios distintos y uno vale 2", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Enumerar las dos configuraciones posibles del espectro", "lado": "conjunto", "depende_de": ["a1", "b1"]},
                {"id": "c2", "enunciado": "Descartar la configuración incompatible con el determinante", "lado": "conjunto", "depende_de": ["c1"]},
                {"id": "c3", "enunciado": "Espectro {2,2,3}: escribir el polinomio característico", "lado": "conjunto", "depende_de": ["c2"]},
            ],
            "paso_final": "c3",
        },
    },
    "El área del paralelogramo que nadie ve entero": {
        "codigo": "al-lagrange-area",
        "respuesta_canonica": "9",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Identidad de Lagrange que vincula ambos productos", "lado": "publico"},
                {"id": "a1", "enunciado": "De las normas: el producto de los cuadrados es 225", "lado": "a", "depende_de": ["p0"]},
                {"id": "b1", "enunciado": "Del producto escalar: su cuadrado es 144", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Restar para obtener el cuadrado de la norma del producto vectorial", "lado": "conjunto", "depende_de": ["a1", "b1"]},
                {"id": "c2", "enunciado": "Tomar raíz cuadrada", "lado": "conjunto", "depende_de": ["c1"]},
            ],
            "paso_final": "c2",
        },
    },
    "Reconstruir el polinomio cúbico": {
        "codigo": "ia-cardano-vieta",
        "respuesta_canonica": "(-6, 11, -6)",
        "tipo_respuesta": "tupla",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Relaciones entre coeficientes y funciones simétricas de las raíces", "lado": "publico"},
                {"id": "a1", "enunciado": "De la suma y la suma de cuadrados: primera y segunda simétricas", "lado": "a", "depende_de": ["p0"]},
                {"id": "a2", "enunciado": "Despejar los coeficientes de segundo y primer grado", "lado": "a", "depende_de": ["a1"]},
                {"id": "b1", "enunciado": "El valor 1 anula el polinomio", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Evaluar en 1 con los coeficientes ya despejados y obtener el término independiente", "lado": "conjunto", "depende_de": ["a2", "b1"]},
                {"id": "c2", "enunciado": "Factorizar el polinomio resultante", "lado": "conjunto", "depende_de": ["c1"]},
            ],
            "paso_final": "c2",
        },
    },
    "Continuidad con parámetros repartidos": {
        "codigo": "ic-continuidad-parametros",
        "respuesta_canonica": "(3, -4, 5)",
        "tipo_respuesta": "tupla",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Para que el cociente sea continuo, el numerador debe anularse en el punto", "lado": "publico"},
                {"id": "a1", "enunciado": "De la continuidad: el numerador es divisible por el denominador", "lado": "a", "depende_de": ["p0"]},
                {"id": "a2", "enunciado": "La función coincide con una recta fuera del punto", "lado": "a", "depende_de": ["a1"]},
                {"id": "b1", "enunciado": "El valor de la función en 3 es 7", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Determinar la recta con el valor conocido", "lado": "conjunto", "depende_de": ["a2", "b1"]},
                {"id": "c2", "enunciado": "Recuperar los parámetros y el valor en el punto de empalme", "lado": "conjunto", "depende_de": ["c1"]},
            ],
            "paso_final": "c2",
        },
    },
    "Optimización de materiales": {
        "codigo": "cdi-caja-presupuesto",
        "respuesta_canonica": "2000*sqrt(3)/3",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Volumen y superficie de la caja sin tapa con base cuadrada", "lado": "publico"},
                {"id": "a1", "enunciado": "De los precios: expresión del costo total", "lado": "a", "depende_de": ["p0"]},
                {"id": "b1", "enunciado": "El presupuesto disponible", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Igualar costo a presupuesto y despejar la altura", "lado": "conjunto", "depende_de": ["a1", "b1"]},
                {"id": "c2", "enunciado": "Volumen como función de un solo lado", "lado": "conjunto", "depende_de": ["c1"]},
                {"id": "c3", "enunciado": "Anular la derivada y verificar que es máximo", "lado": "conjunto", "depende_de": ["c2"]},
            ],
            "paso_final": "c3",
        },
    },
    "Una integral que se arma por partes": {
        "codigo": "cdi-partes-tfc",
        "respuesta_canonica": "4",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Integración por partes deja un término de borde y una integral de la derivada", "lado": "publico"},
                {"id": "a1", "enunciado": "El término de borde queda determinado por la derivada en 1", "lado": "a", "depende_de": ["p0"]},
                {"id": "b1", "enunciado": "La integral de la derivada es la variación de la función", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Restar ambos aportes", "lado": "conjunto", "depende_de": ["a1", "b1"]},
            ],
            "paso_final": "c1",
        },
    },
    "Clasificar un punto crítico a cuatro manos": {
        "codigo": "cvv-punto-critico",
        "respuesta_canonica": "-3",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Gradiente y hessiano de la superficie en función de los parámetros", "lado": "publico"},
                {"id": "a1", "enunciado": "Anular el gradiente en el punto determina el parámetro del término cruzado", "lado": "a", "depende_de": ["p0"]},
                {"id": "a2", "enunciado": "Con ese parámetro, el hessiano clasifica el punto como mínimo local", "lado": "a", "depende_de": ["a1"]},
                {"id": "b1", "enunciado": "El valor en el origen fija el término independiente", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Evaluar la función en el punto con ambos parámetros", "lado": "conjunto", "depende_de": ["a1", "b1"]},
            ],
            "paso_final": "c1",
        },
    },
    "La ecuación y sus condiciones iniciales, por separado": {
        "codigo": "edo-lineal-condiciones",
        "respuesta_canonica": "exp(t) + exp(2*t)",
        "tipo_respuesta": "expresion",
        "estructura_solucion": {
            "pasos": [
                {"id": "p0", "enunciado": "Una lineal homogénea con coeficientes constantes se resuelve por su ecuación característica", "lado": "publico"},
                {"id": "a1", "enunciado": "De la ecuación: raíces características 1 y 2", "lado": "a", "depende_de": ["p0"]},
                {"id": "a2", "enunciado": "Solución general como combinación de las dos exponenciales", "lado": "a", "depende_de": ["a1"]},
                {"id": "b1", "enunciado": "Las condiciones iniciales de posición y velocidad", "lado": "b", "depende_de": ["p0"]},
                {"id": "c1", "enunciado": "Plantear y resolver el sistema para las constantes", "lado": "conjunto", "depende_de": ["a2", "b1"]},
                {"id": "c2", "enunciado": "Escribir la solución explícita", "lado": "conjunto", "depende_de": ["c1"]},
            ],
            "paso_final": "c2",
        },
    },
}

# Correcciones de contenido detectadas al anotar. Se aplican explícitamente y no
# en silencio, porque cambian el hash de la instancia.
CORRECCIONES_ENUNCIADO: dict[str, tuple[str, str]] = {
    # El enunciado pedía det(M - λI), cuyo desarrollo para 3x3 tiene signo
    # opuesto al polinomio mónico que da la resolución. Se unifica al mónico.
    "El polinomio característico oculto": (
        r"p(\lambda) = \det(M - \lambda I)",
        r"p(\lambda) = \det(\lambda I - M)",
    ),
}


class _Volcador(yaml.SafeDumper):
    """Volcador que fuerza estilo de bloque para los textos multilínea."""


def _representar_texto(volcador: yaml.SafeDumper, valor: str):
    estilo = "|" if "\n" in valor else None
    return volcador.represent_scalar("tag:yaml.org,2002:str", valor, style=estilo)


_Volcador.add_representer(str, _representar_texto)


def migrar(base: Path, salida: Path) -> int:
    if not base.exists():
        print(f"No existe la base de origen: {base}", file=sys.stderr)
        return 1

    salida.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(base)
    conexion.row_factory = sqlite3.Row

    filas = conexion.execute(
        "SELECT titulo, categoria, subtema, dificultad, enunciado_base, "
        "dato_a, dato_b, resolucion_latex FROM problemas ORDER BY id"
    ).fetchall()

    if not filas:
        print("La base de origen no tiene problemas.", file=sys.stderr)
        return 1

    escritos = 0
    sin_anotar: list[str] = []

    for fila in filas:
        titulo = fila["titulo"]
        nuevos = CAMPOS_NUEVOS.get(titulo)
        if nuevos is None:
            sin_anotar.append(titulo)
            continue

        enunciado = fila["enunciado_base"]
        if titulo in CORRECCIONES_ENUNCIADO:
            viejo, nuevo = CORRECCIONES_ENUNCIADO[titulo]
            if viejo in enunciado:
                enunciado = enunciado.replace(viejo, nuevo)
                print(f"  · corrección de enunciado aplicada en {titulo!r}")

        documento = {
            "codigo": nuevos["codigo"],
            "titulo": titulo,
            "area": fila["categoria"],
            "subtema": fila["subtema"],
            "dificultad_declarada": fila["dificultad"],
            "enunciado_publico": enunciado,
            "dato_a": fila["dato_a"],
            "dato_b": fila["dato_b"],
            "respuesta_canonica": nuevos["respuesta_canonica"],
            "tipo_respuesta": nuevos["tipo_respuesta"],
            "resolucion_latex": fila["resolucion_latex"],
            "estructura_solucion": nuevos["estructura_solucion"],
        }

        destino = salida / f"{nuevos['codigo']}.yaml"
        destino.write_text(
            yaml.dump(
                documento,
                Dumper=_Volcador,
                allow_unicode=True,
                sort_keys=False,
                width=88,
            ),
            encoding="utf-8",
        )
        escritos += 1
        print(f"  + {destino.name}")

    print(f"\nSe escribieron {escritos} instancia(s) en {salida}")
    if sin_anotar:
        print("\nSin anotar (falta respuesta canónica y DAG):")
        for titulo in sin_anotar:
            print(f"  - {titulo}")
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("plataforma.db"))
    parser.add_argument("--salida", type=Path, default=Path("datos/instancias"))
    args = parser.parse_args()
    raise SystemExit(migrar(args.base, args.salida))
