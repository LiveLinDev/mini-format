"""Configuración común de tests/: ninguna prueba puede llamar a la red.

La fixture ``sin_red`` (automática) hace fallar cualquier intento de abrir una conexión que no sea de bucle
local o de socket Unix. Las pruebas de adaptadores de modelos usan transportes o clientes simulados (MOCK) y nunca
llegan a un proveedor real; ver tests/test_nucleo_adaptadores.py. ``ROOT`` se define también aquí porque las pruebas de
experiments/generativo/tests hacen ``from conftest import ROOT`` y, según el orden de las rutas dadas a pytest, el
módulo ``conftest`` que queda importado puede ser este.
"""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_connect_original = socket.socket.connect
_create_original = socket.create_connection


def _es_local(direccion) -> bool:
    if isinstance(direccion, (str, bytes)):  # socket Unix
        return True
    try:
        return ipaddress.ip_address(direccion[0]).is_loopback or direccion[0] == "localhost"
    except (ValueError, TypeError, IndexError):
        return direccion[0] == "localhost"


def _connect(self, direccion, *args, **kwargs):
    if not _es_local(direccion):
        raise RuntimeError(f"acceso a red prohibido en las pruebas: {direccion!r}")
    return _connect_original(self, direccion, *args, **kwargs)


def _create_connection(direccion, *args, **kwargs):
    if not _es_local(direccion):
        raise RuntimeError(f"acceso a red prohibido en las pruebas: {direccion!r}")
    return _create_original(direccion, *args, **kwargs)


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Cualquier conexión a un destino que no sea local hace fallar la prueba."""
    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket, "create_connection", _create_connection)
    yield
