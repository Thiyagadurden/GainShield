# Assumptions register

The GainShield problem statement fixes the *kind* of plant (bidirectional EV fast-charger DC-link voltage
controller) and the constraint *categories* (voltage, current, stability, switching) but gives **no numerical
values**. Every number below is therefore an **engineering assumption for simulation**, chosen to be
representative of an 800 V-class, ~30 kW charger module. They are **not** ratings of any real product.
All values live in `config/default.toml`; changing them and re-running `experiments/run_all.py` regenerates
every result.

| ID | Parameter | Value | Rationale |
|---|---|---|---|
| A-1 | Module rated power | 30 kW | DC fast chargers are commonly built from 15–40 kW modules; one module is modelled. |
| A-2 | DC-link reference | 800 V | 800 V-class EV platforms; the link must exceed the grid line-line peak (586 V) with headroom. |
| A-3 | DC-link capacitance | 2.0 mF, ±20 % | Stores 640 J (≈21 ms of rated power). ±20 % is required by the problem statement (tolerance + ageing). |
| A-4 | Grid | 415 V L-L, 50 Hz; 0.80–1.10 pu considered | Indian LV three-phase supply; band covers sags and over-voltage. |
| A-5 | Lumped DC-side loss | 20 kΩ equivalent | Bleeder + conduction losses lumped; ≈32 W at 800 V (negligible dynamically). |
| A-6 | AFE efficiency | 98 %, direction-dependent | Typical SiC AFE; applied as P·η when rectifying and P/η when inverting. |
| A-7 | Inner current loop (closed) | τ_i = 0.5 ms nominal, 0.3–1.0 ms | Inner-loop bandwidth ~160–530 Hz, typical for 10 kHz switching. |
| A-8 | DC-DC battery-power loop | τ = 2 ms, slew 2 kW/ms, ±30 kW | Battery-side power is regulated independently ⇒ constant-power behaviour seen from the link. |
| A-9 | Switching and sampling | f_sw = f_s = 10 kHz | Single update per switching period. |
| A-10 | Control delay | 1.5 samples nominal (1 computation + 0.5 PWM), 1.0–2.0 | Standard digital-PWM delay model. |
| A-11 | AFE current limit | 80 A peak (d-axis) | 1.36× the 59 A needed for rated power at 1.0 pu; ~1.1× at 0.8 pu grid. |
| A-12 | Voltage constraints | ±5 % operating band, ±10 % trip, supervisor abort at ±4 %; current violation above 95 % of limit | Typical DC-link tolerance; abort band inside the operating band so the supervisor acts before a violation. |
| A-13 | Stability requirements | worst-case PM ≥ 40°, GM ≥ 6 dB, modulus margin ≥ 0.5 over the uncertainty set | Conventional robustness targets; 40° is a *worst-case* requirement (nominal PM is higher). |
| A-14 | Sensor noise | 1 V (voltage), 0.5 A (current), 1σ | ~0.1 % of full scale; noise-scaled ×2/×3 in tests. |
| A-15 | Context-estimation error bounds | C ±5 %, Vg ±3 %, τ_i ±20 %, delay ±0.2 samples | Used by the context-conditioned certificate. Simulated errors are drawn well inside (C σ = 1.5 %). Assumes C, τ_i and delay are identified at commissioning / online. |

## Model simplifications (what is NOT represented)

* Switching ripple and PWM harmonics (averaged model).
* AC-side LCL/L filter dynamics, PLL dynamics, grid impedance, unbalance and harmonics.
* Battery voltage dynamics and the DC-DC duty-cycle-level dynamics (DC-DC represented by its closed power loop).
* Thermal effects, component ageing during a run, semiconductor losses vs. operating point.
* Protection hardware (pre-charge, contactors, OVP/UVP comparators).

## Stability assumptions

* Certification is for the **linearised small-signal model** (valid while the current reference is not
  saturated). Large-signal behaviour (saturation, CPL nonlinearity) is checked empirically in simulation.
* Tier 1 is a proof over the capacitance / grid-voltage / efficiency interval (zero-exclusion principle) at
  every node of a dense τ_i × delay grid (8 × 11 nodes); between grid nodes it is not proved.
* The lossy term (R_loss) is omitted in the certificate (adds damping, pole at −0.05 rad/s).

## Optimizer assumptions

* Margin GPs use fixed, a-priori hyper-parameters (length-scale 0.15 in normalised gain space); the SafeOpt
  theoretical guarantee additionally needs an RKHS-norm bound that is **not verified** here.
* β = 2, safety threshold h = 0.15 on normalised margins; σ acceptance limit 0.25; gain-step limit ×3.
* The probe episode (+10 V reference step, ±6 kW battery-power step) is assumed acceptable to run during a
  charging session.
* Cost weights (IAE 0.35, peak load deviation 0.25, overshoot 0.10, settling 0.10, ripple 0.20) express a
  design priority; their sensitivity is not studied.

## Validation boundaries

Simulation only. No software-in-the-loop on target hardware, no HIL, no power-stage tests have been run.
