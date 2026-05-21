"""Shared pytest fixtures."""
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db_path(tmp_path):
    """Temporary SQLite DB path."""
    return tmp_path / "test.db"


@pytest.fixture
def fixtures_audio_dir():
    """Path to test audio fixtures directory."""
    return FIXTURES_DIR / "audio"


@pytest.fixture
def sse_samples_dir():
    """Path to recorded SSE sequences."""
    return FIXTURES_DIR / "sse_samples"
