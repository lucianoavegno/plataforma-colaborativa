"""Capa de dominio: funciones puras sobre las que se apoya la medición.

Ningún módulo de este paquete importa FastAPI, SQLAlchemy ni el cliente de
modelos. La separación permite auditar y replicar el cálculo de los indicadores
sin levantar el sistema.
"""
