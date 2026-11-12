import numpy as np
import pytest

from gainshield.plant.charger import ChargerPlant, PlantVariation, mode_of


def test_equilibrium_is_steady(cfg):
    pl = ChargerPlant(cfg)
    x0 = pl.reset(800.0, 15e3)
    for _ in range(200):
        pl.step(x0[1])
    assert abs(pl.x[0] - 800.0) < 1e-6
    assert abs(pl.x[2] - 15e3) < 1e-6


@pytest.mark.parametrize("p", [20e3, -20e3])
def test_energy_balance_open_loop(cfg, p):
    """Change in stored energy equals the integral of the power terms (energy conservation)."""
    pl = ChargerPlant(cfg)
    x0 = pl.reset(800.0, 0.0)
    pl.set_load_demand(p)
    W0 = pl.energy()
    acc = 0.0
    h = pl.h
    for _ in range(40):  # 4 ms open loop, command held
        for _ in range(pl.n_sub):
            pass
        pt0 = pl.power_terms()
        pl.step(x0[1])
        pt1 = pl.power_terms()
        acc += 0.5 * pl.Ts * ((pt0["P_afe_dc"] - pt0["P_dc"] - pt0["P_loss"]) + (pt1["P_afe_dc"] - pt1["P_dc"] - pt1["P_loss"]))
    assert pl.energy() - W0 == pytest.approx(acc, rel=2e-2)


def test_sign_convention(cfg):
    pl = ChargerPlant(cfg)
    x = pl.reset(800.0, 10e3)
    assert x[1] > 0 and mode_of(10e3) == "G2V"      # grid supplies power when charging
    x = pl.reset(800.0, -10e3)
    assert x[1] < 0 and mode_of(-10e3) == "V2G"     # power flows back to grid
    # in V2G, AFE dc power magnitude exceeds ac power (losses on the dc side)
    assert abs(pl.afe_dc_power(-10.0)) > abs(1.5 * pl.Vg_pk_nom * -10.0)


def test_load_step_drops_voltage_open_loop(cfg):
    pl = ChargerPlant(cfg)
    x0 = pl.reset(800.0, 5e3)
    pl.set_load_demand(15e3)
    for _ in range(50):
        pl.step(x0[1])
    assert pl.x[0] < 800.0


def test_delay_line_resolution(cfg):
    pl = ChargerPlant(cfg, PlantVariation(delay_samples=1.5))
    assert pl.delay_sub == 15
    pl.reset(800.0, 0.0)
    i0 = pl.x[1]
    pl.step(i0 + 10.0)
    # after one period only (1 - 1.5) < 0 of the command has arrived -> current unchanged
    assert pl.x[1] == pytest.approx(i0, abs=1e-9)
    pl.step(i0 + 10.0)
    assert pl.x[1] > i0


def test_nonphysical_parameters_rejected(cfg):
    with pytest.raises(ValueError):
        ChargerPlant(cfg, PlantVariation(C_pu=0.0))
