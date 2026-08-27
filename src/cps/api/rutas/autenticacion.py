"""Cuentas, sesión y consentimiento informado."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from cps.api import esquemas
from cps.api.seguridad import (
    crear_token,
    cuenta_actual,
    generar_seudonimo,
    hashear_password,
    verificar_password,
)
from cps.db import obtener_sesion
from cps.modelos.base import ahora
from cps.modelos.entidades import Consentimiento, Cuenta, Rol

router = APIRouter(prefix="/api/auth", tags=["cuentas"])

VERSION_CONSENTIMIENTO = "1.0"

TEXTO_CONSENTIMIENTO = """\
Participación en el estudio sobre resolución colaborativa de problemas

Qué se recolecta. Las transcripciones completas de los diálogos en los que
participes, las respuestas que envíes, los tiempos de cada intervención y el
resultado de la verificación automática de tus respuestas.

Cómo se identifica. Tus datos se guardan asociados a un seudónimo. Tu nombre y
tu correo electrónico no aparecen en ningún archivo de análisis ni en ninguna
publicación derivada del estudio.

Con quién dialogás. Tu interlocutor en los ejercicios es un sistema
automático, no una persona.

Uso previsto. Los datos se emplean para investigación sobre el diseño de
problemas colaborativos. Podrán publicarse resultados agregados y, si se
publicaran transcripciones, será en forma seudonimizada.

Sin consecuencia académica. La participación es voluntaria y está desvinculada
de toda calificación. Ni tu desempeño ni tu decisión de no participar tienen
efecto curricular alguno.

Retiro. Podés retirar tu consentimiento en cualquier momento y solicitar el
borrado de tus episodios, sin dar explicaciones y sin consecuencia.
"""


def _hash_consentimiento() -> str:
    return hashlib.sha256(TEXTO_CONSENTIMIENTO.encode("utf-8")).hexdigest()


@router.get("/consentimiento", response_model=esquemas.TextoConsentimiento)
def texto_consentimiento() -> esquemas.TextoConsentimiento:
    """Texto vigente. Se expone para poder mostrarlo antes de aceptarlo."""
    return esquemas.TextoConsentimiento(
        version=VERSION_CONSENTIMIENTO,
        hash=_hash_consentimiento(),
        cuerpo=TEXTO_CONSENTIMIENTO,
    )


def _autenticar(sesion: Session, email: str, password: str) -> Cuenta:
    cuenta = sesion.scalar(select(Cuenta).where(Cuenta.email == email.lower()))
    if cuenta is None or not verificar_password(password, cuenta.hash_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    return cuenta


@router.post("/registro", response_model=esquemas.Token, status_code=201)
def registro(
    datos: esquemas.CuentaCrear, sesion: Session = Depends(obtener_sesion)
) -> esquemas.Token:
    """Crea una cuenta y registra el consentimiento en la misma transacción.

    El consentimiento no es una casilla en el perfil: es una fila con la versión
    y el hash del texto aceptado, porque si el texto cambia hay que poder saber
    qué aceptó cada persona.
    """
    email = datos.email.lower()
    if sesion.scalar(select(Cuenta).where(Cuenta.email == email)):
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese email")

    cuenta = Cuenta(
        email=email,
        nombre=datos.nombre.strip(),
        hash_password=hashear_password(datos.password),
        rol=Rol.PARTICIPANTE,
        seudonimo=generar_seudonimo(email),
    )
    sesion.add(cuenta)
    sesion.flush()

    sesion.add(
        Consentimiento(
            cuenta_id=cuenta.id,
            version_texto=VERSION_CONSENTIMIENTO,
            hash_texto=_hash_consentimiento(),
        )
    )
    sesion.commit()
    sesion.refresh(cuenta)

    return esquemas.Token(
        access_token=crear_token(cuenta),
        cuenta=esquemas.CuentaSalida.model_validate(cuenta),
    )


@router.post("/login", response_model=esquemas.Token)
def login(
    datos: esquemas.CuentaLogin, sesion: Session = Depends(obtener_sesion)
) -> esquemas.Token:
    cuenta = _autenticar(sesion, datos.email, datos.password)
    return esquemas.Token(
        access_token=crear_token(cuenta),
        cuenta=esquemas.CuentaSalida.model_validate(cuenta),
    )


@router.post("/token", response_model=esquemas.Token, include_in_schema=False)
def login_formulario(
    formulario: OAuth2PasswordRequestForm = Depends(),
    sesion: Session = Depends(obtener_sesion),
) -> esquemas.Token:
    """Variante con formulario, para el botón Authorize de la documentación."""
    cuenta = _autenticar(sesion, formulario.username, formulario.password)
    return esquemas.Token(
        access_token=crear_token(cuenta),
        cuenta=esquemas.CuentaSalida.model_validate(cuenta),
    )


@router.get("/yo", response_model=esquemas.CuentaSalida)
def yo(cuenta: Cuenta = Depends(cuenta_actual)) -> Cuenta:
    return cuenta


@router.post("/retirar-consentimiento", status_code=204)
def retirar_consentimiento(
    cuenta: Cuenta = Depends(cuenta_actual), sesion: Session = Depends(obtener_sesion)
) -> None:
    """Marca el consentimiento como retirado.

    No borra la fila: hay que poder demostrar que el retiro se registró y
    cuándo. El borrado efectivo de los episodios se ejecuta por separado, desde
    la línea de comandos, para que quede como acto deliberado del investigador.
    """
    vigentes = [c for c in cuenta.consentimientos if c.vigente]
    if not vigentes:
        raise HTTPException(status_code=409, detail="No hay consentimiento vigente")
    for consentimiento in vigentes:
        consentimiento.retirado_en = ahora()
    sesion.commit()
