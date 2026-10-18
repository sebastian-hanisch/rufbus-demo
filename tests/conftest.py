"""Gemeinsame Fixtures: die Mini-Instanz, an der jede Einheit von Hand geprüft wird (DEMO-PLAYBOOK §1b)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ruf_constants as C  # noqa: E402


@pytest.fixture
def tt3():
    """Drei Haltepunkte auf einer Geraden, 3 km Abstand bei 30 km/h = 6 min zwischen Nachbarn, 12 min zwischen den Enden."""
    return [[0.0, 6.0, 12.0], [6.0, 0.0, 6.0], [12.0, 6.0, 0.0]]


@pytest.fixture
def dw():
    return C.DWELL
