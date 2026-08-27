"""Carga y versionado del banco de instancias.

Las instancias se definen en archivos YAML bajo ``datos/instancias/`` y no en un
script de Python. La diferencia importa: un archivo de datos se puede revisar en
un diff, validar contra un esquema y citar por su hash, mientras que un literal
dentro de un script sólo se puede leer ejecutándolo.

El versionado es por contenido. Cada instancia lleva un hash de sus campos
sustantivos; si alguno cambia, la instancia se vuelve a publicar con versión
nueva y la anterior se desactiva. Las mediciones ya calculadas conservan el hash
que tenían al medirse, de modo que siempre se puede saber si una medición
corresponde al contenido actual o a uno anterior.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cps.dominio.areas import es_area_valida
from cps.dominio.dag import EstructuraSolucion, Lado, Paso
from cps.dominio.verificacion import TipoRespuesta, verificar

__all__ = [
    "DefinicionInstancia",
    "ErrorDeBanco",
    "cargar_directorio",
    "cargar_estructura",
    "hash_instancia",
    "serializar_estructura",
]


class ErrorDeBanco(ValueError):
    """Un archivo del banco es inválido."""


CAMPOS_REQUERIDOS = (
    "codigo",
    "titulo",
    "area",
    "enunciado_publico",
    "dato_a",
    "dato_b",
    "respuesta_canonica",
    "resolucion_latex",
)


def hash_instancia(
    enunciado: str, dato_a: str, dato_b: str, respuesta_canonica: str
) -> str:
    """Hash del contenido sustantivo de una instancia.

    Incluye lo que puede alterar una medición y excluye lo que no: el título y
    el subtema pueden corregirse sin invalidar la calibración.
    """
    material = "\x00".join(
        [enunciado.strip(), dato_a.strip(), dato_b.strip(), respuesta_canonica.strip()]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def cargar_estructura(datos: dict[str, Any]) -> EstructuraSolucion:
    """Construye el DAG desde su representación serializada."""
    pasos_crudos = datos.get("pasos")
    if not isinstance(pasos_crudos, list) or not pasos_crudos:
        raise ErrorDeBanco("La estructura de solución no tiene pasos")

    pasos = []
    for crudo in pasos_crudos:
        try:
            pasos.append(
                Paso(
                    id=str(crudo["id"]),
                    enunciado=str(crudo.get("enunciado", "")),
                    lado=Lado(crudo["lado"]),
                    depende_de=tuple(str(d) for d in crudo.get("depende_de", [])),
                )
            )
        except (KeyError, ValueError) as exc:
            raise ErrorDeBanco(f"Paso inválido en la estructura: {crudo!r} ({exc})") from exc

    final = datos.get("paso_final") or pasos[-1].id
    return EstructuraSolucion(pasos=tuple(pasos), paso_final=str(final))


def serializar_estructura(estructura: EstructuraSolucion) -> dict[str, Any]:
    """Representación JSON del DAG, para guardar en la base."""
    return {
        "pasos": [
            {
                "id": paso.id,
                "enunciado": paso.enunciado,
                "lado": paso.lado.value,
                "depende_de": list(paso.depende_de),
            }
            for paso in estructura.pasos
        ],
        "paso_final": estructura.paso_final,
    }


@dataclass(frozen=True, slots=True)
class DefinicionInstancia:
    """Una instancia leída de disco, ya validada."""

    codigo: str
    titulo: str
    area: str
    subtema: str | None
    dificultad_declarada: int
    enunciado_publico: str
    dato_a: str
    dato_b: str
    respuesta_canonica: str
    tipo_respuesta: TipoRespuesta
    resolucion_latex: str
    estructura: EstructuraSolucion
    origen: Path

    @property
    def hash_contenido(self) -> str:
        return hash_instancia(
            self.enunciado_publico, self.dato_a, self.dato_b, self.respuesta_canonica
        )

    def advertencias(self) -> list[str]:
        """Problemas de diseño detectables sin correr el solver."""
        return self.estructura.verificar_particion_genuina()


def normalizar_bloques(texto: str) -> str:
    """Pasa las fórmulas ``$$...$$`` de una línea a la forma de bloque.

    El renderizador sólo centra la matemática cuando los delimitadores están en
    líneas propias. Escrito en una sola línea lo trata como matemática en línea y
    el desarrollo queda pegado al párrafo anterior.
    """
    salida: list[str] = []
    for linea in texto.split("\n"):
        limpia = linea.strip()
        if limpia.startswith("$$") and limpia.endswith("$$") and len(limpia) > 4:
            salida += ["", "$$", limpia[2:-2].strip(), "$$", ""]
        else:
            salida.append(linea)

    resultado: list[str] = []
    for linea in salida:
        if not linea.strip() and resultado and not resultado[-1].strip():
            continue
        resultado.append(linea)
    return "\n".join(resultado).strip()


def cargar_archivo(ruta: Path) -> DefinicionInstancia:
    """Lee y valida un archivo de instancia.

    La validación incluye una comprobación que suele olvidarse: que la propia
    respuesta canónica sea parseable. Si no lo fuera, todos los episodios de esa
    instancia darían "no verificable" y el fallo aparecería recién al analizar.
    """
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErrorDeBanco(f"{ruta.name}: YAML inválido ({exc})") from exc

    if not isinstance(datos, dict):
        raise ErrorDeBanco(f"{ruta.name}: se esperaba un objeto en la raíz")

    faltantes = [campo for campo in CAMPOS_REQUERIDOS if not datos.get(campo)]
    if faltantes:
        raise ErrorDeBanco(f"{ruta.name}: faltan campos obligatorios: {', '.join(faltantes)}")

    area = str(datos["area"])
    if not es_area_valida(area):
        raise ErrorDeBanco(f"{ruta.name}: área desconocida {area!r}")

    try:
        tipo = TipoRespuesta(datos.get("tipo_respuesta", "expresion"))
    except ValueError as exc:
        raise ErrorDeBanco(f"{ruta.name}: tipo_respuesta inválido ({exc})") from exc

    respuesta = str(datos["respuesta_canonica"]).strip()
    try:
        verificar(respuesta, respuesta, tipo)
    except ValueError as exc:
        raise ErrorDeBanco(
            f"{ruta.name}: la respuesta canónica no es interpretable ({exc}). "
            "Toda verificación de esta instancia fallaría."
        ) from exc

    if "estructura_solucion" not in datos:
        raise ErrorDeBanco(
            f"{ruta.name}: falta 'estructura_solucion'. Sin el DAG anotado no se "
            "pueden calcular la emergencia ni la cota de rondas."
        )

    try:
        estructura = cargar_estructura(datos["estructura_solucion"])
    except ErrorDeBanco as exc:
        raise ErrorDeBanco(f"{ruta.name}: {exc}") from exc

    dificultad = int(datos.get("dificultad_declarada", 3))
    if not 1 <= dificultad <= 5:
        raise ErrorDeBanco(f"{ruta.name}: dificultad_declarada fuera de 1..5")

    return DefinicionInstancia(
        codigo=str(datos["codigo"]),
        titulo=str(datos["titulo"]),
        area=area,
        subtema=str(datos["subtema"]) if datos.get("subtema") else None,
        dificultad_declarada=dificultad,
        enunciado_publico=normalizar_bloques(str(datos["enunciado_publico"])),
        dato_a=normalizar_bloques(str(datos["dato_a"])),
        dato_b=normalizar_bloques(str(datos["dato_b"])),
        respuesta_canonica=respuesta,
        tipo_respuesta=tipo,
        resolucion_latex=normalizar_bloques(str(datos["resolucion_latex"])),
        estructura=estructura,
        origen=ruta,
    )


def cargar_directorio(directorio: Path) -> list[DefinicionInstancia]:
    """Lee todas las instancias del directorio, en orden estable por nombre.

    Falla ante el primer archivo inválido en lugar de saltearlo: un banco cargado
    a medias es peor que uno que no carga, porque el faltante pasa inadvertido.
    """
    if not directorio.is_dir():
        raise ErrorDeBanco(f"No existe el directorio de instancias: {directorio}")

    archivos = sorted(directorio.glob("*.yaml")) + sorted(directorio.glob("*.yml"))
    if not archivos:
        raise ErrorDeBanco(f"No hay archivos de instancia en {directorio}")

    definiciones = [cargar_archivo(ruta) for ruta in archivos]

    codigos = [d.codigo for d in definiciones]
    duplicados = {c for c in codigos if codigos.count(c) > 1}
    if duplicados:
        raise ErrorDeBanco(f"Códigos de instancia duplicados: {sorted(duplicados)}")

    return definiciones
