"""Configuración común: rutas y bloqueo de red durante las pruebas."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
for p in (ROOT / "src", EXP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Cualquier intento de abrir una conexión de red hace fallar la prueba."""
    def _prohibido(*args, **kwargs):
        raise RuntimeError("acceso a red prohibido en las pruebas")
    monkeypatch.setattr(socket.socket, "connect", _prohibido)
    monkeypatch.setattr(socket, "create_connection", _prohibido)
    yield


@pytest.fixture
def sin_claves(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield
