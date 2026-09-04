from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_csv() -> Path:
    return ROOT / "examples" / "sample_pl.csv"


@pytest.fixture
def sample_mpm() -> Path:
    return ROOT / "examples" / "sample_pl.mpm.yaml"
