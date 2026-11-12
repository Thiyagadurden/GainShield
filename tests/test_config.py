import pytest

from gainshield.config import DEFAULT_CONFIG, load_config


def test_default_config_loads(cfg):
    assert cfg.plant.Vdc_ref_V == 800.0
    assert cfg.converter.Ts == pytest.approx(1e-4)
    assert cfg.supervisor.V_abort_frac < cfg.constraints.V_band_op < cfg.constraints.V_band_trip


def test_invalid_config_rejected(tmp_path):
    txt = DEFAULT_CONFIG.read_text().replace("V_abort_frac     = 0.04", "V_abort_frac     = 0.08")
    p = tmp_path / "bad.toml"
    p.write_text(txt)
    with pytest.raises(ValueError, match="abort band"):
        load_config(p)
