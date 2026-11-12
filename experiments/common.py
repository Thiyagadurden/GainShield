"""Shared helpers for experiment scripts (paths, model persistence)."""
from __future__ import annotations

import json
import pickle
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gainshield.config import Config, load_config  # noqa: E402
from gainshield.core import GainShield, GainShieldFlags  # noqa: E402
from gainshield.stability.certify import Certificate, compute_certificate  # noqa: E402

RESULTS = ROOT / "results"
FIGS = RESULTS / "figures"
CERT_PATH = RESULTS / "certificate.npz"
MODEL_PATH = RESULTS / "gainshield_model.pkl"


def get_certificate(cfg: Config, recompute: bool = False) -> Certificate:
    if recompute or not CERT_PATH.exists():
        cert = compute_certificate(cfg)
        RESULTS.mkdir(exist_ok=True)
        cert.save(str(CERT_PATH))
        return cert
    return Certificate.load(str(CERT_PATH))


def save_model(gs: GainShield, path: Path = MODEL_PATH) -> None:
    with open(path, "wb") as fh:
        pickle.dump({"bo": gs.bo, "scales": gs.scales, "flags": gs.flags}, fh)


def load_model(cfg: Config, cert: Certificate, path: Path = MODEL_PATH, audit=None) -> GainShield:
    """Load a trained model. Only load pickles produced by this repository."""
    with open(path, "rb") as fh:
        d = pickle.load(fh)
    gs = GainShield(cfg, cert, flags=d["flags"], audit=audit)
    gs.bo = d["bo"]
    gs.scales = d["scales"]
    return gs


def env_info() -> dict:
    import numpy, scipy, sklearn, pandas, matplotlib
    return {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__, "pandas": pandas.__version__,
            "matplotlib": matplotlib.__version__, "platform": platform.platform(),
            "cpu": platform.processor() or platform.machine()}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float))


__all__ = ["ROOT", "RESULTS", "FIGS", "load_config", "get_certificate", "save_model", "load_model",
           "GainShield", "GainShieldFlags", "env_info", "write_json"]
