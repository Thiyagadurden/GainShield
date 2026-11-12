import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from gainshield.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def cert(cfg):
    """Coarse certificate (fast) for unit tests."""
    from gainshield.stability.certify import compute_certificate
    return compute_certificate(cfg, n=15, mc_samples=40)
