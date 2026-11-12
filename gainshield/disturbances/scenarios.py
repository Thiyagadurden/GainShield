"""Configurable, seeded disturbance suite.

A ``Scenario`` is pure data: initial operating point, timed events, plant
variation and noise scaling. The same Scenario object (and seed) is given to
every controller under test, which guarantees identical operating conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

from ..plant.charger import PlantVariation

EventKind = Literal["p_load", "vg", "vref"]


@dataclass(frozen=True)
class Event:
    t: float            # [s]
    kind: EventKind     # p_load [W] | vg [pu] | vref [V]
    value: float


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    duration_s: float
    p_load0_W: float
    vg0_pu: float = 1.0
    events: tuple[Event, ...] = ()
    variation: PlantVariation = field(default_factory=PlantVariation)
    noise_scale: float = 1.0
    category: str = "load"

    @property
    def first_event_t(self) -> float:
        return min((e.t for e in self.events), default=0.0)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["events"] = [asdict(e) for e in self.events]
        return d


def _ld(t: float, p: float) -> Event:
    return Event(t, "p_load", p)


def standard_suite() -> list[Scenario]:
    """The 10 required disturbance classes (capacitance split into -20 %/+20 %)."""
    T = 0.30
    t0 = 0.05
    return [
        Scenario("load_increase", "G2V load step 5 -> 20 kW", T, 5e3, events=(_ld(t0, 20e3),)),
        Scenario("load_decrease", "G2V load step 20 -> 5 kW", T, 20e3, events=(_ld(t0, 5e3),)),
        Scenario("g2v_to_v2g", "Power reversal +15 kW -> -15 kW (DC-DC slew 2 kW/ms)", T, 15e3,
                 events=(_ld(t0, -15e3),), category="reversal"),
        Scenario("v2g_to_g2v", "Power reversal -15 kW -> +15 kW", T, -15e3,
                 events=(_ld(t0, 15e3),), category="reversal"),
        Scenario("grid_sag", "Grid sag 1.0 -> 0.80 pu at 20 kW, recovery at 0.20 s", T, 20e3,
                 events=(Event(t0, "vg", 0.80), Event(0.20, "vg", 1.0)), category="grid"),
        Scenario("sensor_noise", "3x sensor noise, load step 10 -> 20 kW", T, 10e3,
                 events=(_ld(t0, 20e3),), noise_scale=3.0, category="noise"),
        Scenario("cap_minus20", "C = -20 %, load step 5 -> 20 kW", T, 5e3,
                 events=(_ld(t0, 20e3),), variation=PlantVariation(C_pu=0.8), category="model"),
        Scenario("cap_plus20", "C = +20 %, load step 5 -> 20 kW", T, 5e3,
                 events=(_ld(t0, 20e3),), variation=PlantVariation(C_pu=1.2), category="model"),
        Scenario("inner_lag_slow", "Inner-loop tau_i = 1.0 ms, load step 5 -> 20 kW", T, 5e3,
                 events=(_ld(t0, 20e3),), variation=PlantVariation(tau_i_s=1.0e-3), category="model"),
        Scenario("delay_long", "Control delay 2.0 samples, load step 5 -> 20 kW", T, 5e3,
                 events=(_ld(t0, 20e3),), variation=PlantVariation(delay_samples=2.0), category="model"),
        Scenario("combined", "C -20 %, tau_i 1 ms, delay 2.0, 2x noise, 0.85 pu sag, then reversal",
                 0.40, 12e3,
                 events=(Event(0.05, "vg", 0.85), _ld(0.15, -12e3), _ld(0.28, 18e3)),
                 variation=PlantVariation(C_pu=0.8, tau_i_s=1.0e-3, delay_samples=2.0),
                 noise_scale=2.0, category="combined"),
    ]


def scenario_by_name(name: str) -> Scenario:
    for s in standard_suite():
        if s.name == name:
            return s
    raise KeyError(f"unknown scenario {name!r}; available: {[s.name for s in standard_suite()]}")


def probe_scenario(p_load_W: float, vg_pu: float, variation: PlantVariation, step_W: float = 6e3,
                   noise_scale: float = 1.0) -> Scenario:
    """Short tuning episode used by the optimizer.

    A +10 V reference step (1.25 %) at 20 ms followed by a moderate battery-power
    step at 90 ms. The power step direction is chosen to stay within the DC-DC
    rating. This is the 'probe' a field tuner could schedule during a session.
    """
    sign = 1.0 if p_load_W <= 15e3 else -1.0
    return Scenario(
        "probe", "tuning probe: +10 V ref step, then power step", 0.17, p_load_W, vg0_pu=vg_pu,
        events=(Event(0.02, "vref", 810.0), _ld(0.09, p_load_W + sign * step_W)),
        variation=variation, noise_scale=noise_scale, category="probe",
    )
