"""Gestión de cuentas y cumplimiento del retiro de consentimiento."""

from __future__ import annotations

import sys

from sqlalchemy import select

from cps.api.seguridad import generar_seudonimo, hashear_password
from cps.db import sesion_de_trabajo
from cps.modelos.entidades import Cuenta, Episodio, Rol


def promover(email: str) -> int:
    with sesion_de_trabajo() as sesion:
        cuenta = sesion.scalar(select(Cuenta).where(Cuenta.email == email.lower()))
        if cuenta is None:
            print(f"No existe una cuenta con el email {email}", file=sys.stderr)
            return 1
        cuenta.rol = Rol.INVESTIGADOR
        print(f"{cuenta.email} ahora tiene rol de investigador.")
    return 0


def crear_investigador(email: str, nombre: str, password: str) -> int:
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.", file=sys.stderr)
        return 1

    with sesion_de_trabajo() as sesion:
        if sesion.scalar(select(Cuenta).where(Cuenta.email == email.lower())):
            print(f"Ya existe una cuenta con el email {email}", file=sys.stderr)
            return 1

        cuenta = Cuenta(
            email=email.lower(),
            nombre=nombre,
            hash_password=hashear_password(password),
            rol=Rol.INVESTIGADOR,
            seudonimo=generar_seudonimo(email),
        )
        sesion.add(cuenta)
        print(f"Cuenta de investigador creada: {email} (seudónimo {cuenta.seudonimo})")
    return 0


def purgar_retirados(*, confirmar: bool = False) -> int:
    """Borra los episodios de quienes retiraron el consentimiento.

    Es un acto deliberado y no automático: el retiro se registra en el momento
    en que la persona lo pide, pero el borrado efectivo lo ejecuta el
    investigador, que es quien responde por la integridad del conjunto de datos.
    """
    with sesion_de_trabajo() as sesion:
        cuentas = sesion.scalars(select(Cuenta)).all()
        afectadas = [
            c
            for c in cuentas
            if c.consentimientos and not any(x.vigente for x in c.consentimientos)
        ]

        if not afectadas:
            print("No hay cuentas con el consentimiento retirado.")
            return 0

        total = 0
        for cuenta in afectadas:
            episodios = sesion.scalars(
                select(Episodio).where(Episodio.cuenta_id == cuenta.id)
            ).all()
            print(f"  {cuenta.seudonimo}: {len(episodios)} episodio(s)")
            total += len(episodios)
            if confirmar:
                for episodio in episodios:
                    sesion.delete(episodio)

        if confirmar:
            print(f"\nSe borraron {total} episodio(s) de {len(afectadas)} cuenta(s).")
        else:
            print(
                f"\nSe borrarían {total} episodio(s) de {len(afectadas)} cuenta(s). "
                "Volvé a correr con --confirmar para ejecutarlo."
            )
    return 0
