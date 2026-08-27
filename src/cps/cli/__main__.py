"""Línea de comandos del instrumento.

El protocolo experimental vive acá y no en la interfaz web, por una razón de
diseño: calibrar una instancia son 120 llamadas al modelo y codificar un lote son
otras tantas. Son procedimientos que se corren de forma deliberada, se registran
y se pueden repetir, no acciones de un botón.

    cps banco validar          Valida los archivos del banco sin tocar la base
    cps banco sembrar          Publica el banco en la base, versionando por contenido
    cps calibrar               Estima la competencia del solver por instancia
    cps codificar              Codifica transcripts con los modelos jueces
    cps divulgacion            Localiza el turno de divulgación de cada dato
    cps exportar               Vuelca los episodios a JSON por líneas
    cps cuenta promover        Da rol de investigador a una cuenta
    cps purgar-retirados       Borra episodios de quienes retiraron el consentimiento
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cps.cli import banco, calibracion, codificacion, cuentas, exportacion

RAIZ = Path(__file__).resolve().parents[3]
DIRECTORIO_INSTANCIAS = RAIZ / "datos" / "instancias"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cps",
        description="Instrumento experimental de resolución colaborativa de problemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subcomandos = parser.add_subparsers(dest="comando", required=True)

    # -- banco ---------------------------------------------------------------
    p_banco = subcomandos.add_parser("banco", help="Gestión del banco de instancias")
    sub_banco = p_banco.add_subparsers(dest="subcomando", required=True)

    p_validar = sub_banco.add_parser(
        "validar", help="Valida los archivos sin escribir en la base"
    )
    p_validar.add_argument("--directorio", type=Path, default=DIRECTORIO_INSTANCIAS)

    p_sembrar = sub_banco.add_parser("sembrar", help="Publica el banco en la base")
    p_sembrar.add_argument("--directorio", type=Path, default=DIRECTORIO_INSTANCIAS)
    p_sembrar.add_argument(
        "--forzar",
        action="store_true",
        help="Publica aunque haya advertencias de diseño en alguna instancia.",
    )

    # -- calibrar ------------------------------------------------------------
    p_calibrar = subcomandos.add_parser(
        "calibrar", help="Estima la función de competencia del solver de referencia"
    )
    p_calibrar.add_argument(
        "--codigo", action="append", help="Limita a estas instancias (repetible)."
    )
    p_calibrar.add_argument("--ensayos", type=int, default=None)
    p_calibrar.add_argument(
        "--recalcular",
        action="store_true",
        help="Vuelve a medir aunque ya exista una medición con la huella vigente.",
    )
    p_calibrar.add_argument(
        "--permitir-simulado",
        action="store_true",
        help="Corre sin credencial de modelo. Sirve para probar el circuito, no para medir.",
    )

    # -- codificar -----------------------------------------------------------
    p_codificar = subcomandos.add_parser(
        "codificar", help="Codifica transcripts con los modelos jueces"
    )
    p_codificar.add_argument("--limite", type=int, default=None)
    p_codificar.add_argument(
        "--recodificar", action="store_true", help="Rehace codificaciones existentes."
    )
    p_codificar.add_argument("--permitir-simulado", action="store_true")

    # -- divulgación ---------------------------------------------------------
    p_divulgacion = subcomandos.add_parser(
        "divulgacion", help="Localiza en qué turno se volcó cada dato privado"
    )
    p_divulgacion.add_argument("--limite", type=int, default=None)
    p_divulgacion.add_argument("--permitir-simulado", action="store_true")

    # -- exportar ------------------------------------------------------------
    p_exportar = subcomandos.add_parser("exportar", help="Vuelca los episodios a JSONL")
    p_exportar.add_argument("--salida", type=Path, default=RAIZ / "datos" / "episodios.jsonl")
    p_exportar.add_argument("--incluir-simulados", action="store_true")
    p_exportar.add_argument("--sin-transcripts", action="store_true")

    # -- cuentas -------------------------------------------------------------
    p_cuenta = subcomandos.add_parser("cuenta", help="Gestión de cuentas")
    sub_cuenta = p_cuenta.add_subparsers(dest="subcomando", required=True)

    p_promover = sub_cuenta.add_parser("promover", help="Otorga rol de investigador")
    p_promover.add_argument("email")

    p_crear = sub_cuenta.add_parser("crear-investigador", help="Crea una cuenta con ese rol")
    p_crear.add_argument("email")
    p_crear.add_argument("nombre")
    p_crear.add_argument("--password", required=True)

    # -- purga ---------------------------------------------------------------
    p_purgar = subcomandos.add_parser(
        "purgar-retirados",
        help="Borra los episodios de cuentas que retiraron el consentimiento",
    )
    p_purgar.add_argument(
        "--confirmar",
        action="store_true",
        help="Sin este flag sólo informa qué borraría.",
    )

    subcomandos.add_parser("estado", help="Muestra la configuración vigente")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    try:
        return _despachar(args)
    except KeyboardInterrupt:
        print("\nInterrumpido.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _despachar(args: argparse.Namespace) -> int:
    if args.comando == "banco":
        if args.subcomando == "validar":
            return banco.validar(args.directorio)
        return banco.sembrar(args.directorio, forzar=args.forzar)

    if args.comando == "calibrar":
        return calibracion.calibrar(
            codigos=args.codigo,
            ensayos=args.ensayos,
            recalcular=args.recalcular,
            permitir_simulado=args.permitir_simulado,
        )

    if args.comando == "codificar":
        return codificacion.codificar(
            limite=args.limite,
            recodificar=args.recodificar,
            permitir_simulado=args.permitir_simulado,
        )

    if args.comando == "divulgacion":
        return codificacion.analizar_divulgacion(
            limite=args.limite, permitir_simulado=args.permitir_simulado
        )

    if args.comando == "exportar":
        return exportacion.exportar(
            salida=args.salida,
            incluir_simulados=args.incluir_simulados,
            incluir_transcripts=not args.sin_transcripts,
        )

    if args.comando == "cuenta":
        if args.subcomando == "promover":
            return cuentas.promover(args.email)
        return cuentas.crear_investigador(args.email, args.nombre, args.password)

    if args.comando == "purgar-retirados":
        return cuentas.purgar_retirados(confirmar=args.confirmar)

    if args.comando == "estado":
        from cps.agentes.motor import obtener_motor
        from cps.agentes.protocolo import VERSION_PROTOCOLO
        from cps.config import obtener_config

        config = obtener_config()
        motor = obtener_motor()
        print(
            json.dumps(
                {
                    "version_protocolo": VERSION_PROTOCOLO,
                    "huella_experimental": config.huella_experimental(),
                    "base_datos": config.url_base_datos,
                    "modelo_participante": config.modelo_participante,
                    "modelo_solver": config.modelo_solver,
                    "modelos_juez": config.modelos_juez,
                    "ensayos_por_celda": config.ensayos_por_celda,
                    "semilla": config.semilla_aleatorizacion,
                    "modelos_simulados": motor.simulado,
                    "motivo": motor.motivo_simulacion,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    raise ValueError(f"Comando no reconocido: {args.comando}")


if __name__ == "__main__":
    raise SystemExit(main())
