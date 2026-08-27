"""Autenticación, autorización y seudonimización.

La autorización acá no es comodidad de producto sino protección de datos. Hay
dos cosas que el sistema no debe permitir:

* que un participante lea los datos privados de una instancia que todavía no
  resolvió, porque eso invalida sus episodios futuros sobre ella;
* que alguien que no sea investigador acceda a episodios ajenos o al banco
  completo.

La versión anterior del sistema exigía únicamente estar autenticado para crear
problemas y reescribir análisis, con lo cual cualquier cuenta registrada podía
alterar el instrumento.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from cps.config import obtener_config
from cps.db import obtener_sesion
from cps.modelos.base import ahora
from cps.modelos.entidades import Cuenta, Rol

# bcrypt sólo considera los primeros 72 bytes.
LIMITE_BCRYPT = 72

esquema_oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o sesión expirada",
    headers={"WWW-Authenticate": "Bearer"},
)

PERMISO_INSUFICIENTE = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Esta operación requiere una cuenta de investigador",
)


def hashear_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:LIMITE_BCRYPT], bcrypt.gensalt()).decode()


def verificar_password(password: str, hash_guardado: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:LIMITE_BCRYPT], hash_guardado.encode())
    except ValueError:
        return False


def generar_seudonimo(email: str) -> str:
    """Seudónimo estable y no reversible para una cuenta.

    Se deriva del correo con HMAC bajo la clave del sistema, más un sufijo
    aleatorio para evitar que dos despliegues con la misma clave produzcan el
    mismo seudónimo para la misma persona. Es el único identificador que
    aparece en las exportaciones: el correo no sale nunca del sistema.
    """
    config = obtener_config()
    digest = hmac.new(
        config.clave_secreta.encode("utf-8"),
        email.lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12]
    return f"p-{digest}-{secrets.token_hex(2)}"


def crear_token(cuenta: Cuenta) -> str:
    config = obtener_config()
    expira = ahora() + timedelta(minutes=config.minutos_expiracion_token)
    carga = {
        "sub": str(cuenta.id),
        "rol": cuenta.rol,
        "exp": expira,
    }
    return jwt.encode(carga, config.clave_secreta, algorithm=config.algoritmo_jwt)


def cuenta_actual(
    token: str | None = Depends(esquema_oauth),
    sesion: Session = Depends(obtener_sesion),
) -> Cuenta:
    """Cuenta autenticada. Falla con 401 si no hay token válido."""
    if not token:
        raise CREDENCIALES_INVALIDAS

    config = obtener_config()
    try:
        carga = jwt.decode(token, config.clave_secreta, algorithms=[config.algoritmo_jwt])
        cuenta_id = int(carga["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise CREDENCIALES_INVALIDAS from exc

    cuenta = sesion.get(Cuenta, cuenta_id)
    if cuenta is None:
        raise CREDENCIALES_INVALIDAS
    return cuenta


def investigador_actual(cuenta: Cuenta = Depends(cuenta_actual)) -> Cuenta:
    """Exige rol de investigador. Protege el banco y los datos agregados."""
    if cuenta.rol != Rol.INVESTIGADOR:
        raise PERMISO_INSUFICIENTE
    return cuenta
