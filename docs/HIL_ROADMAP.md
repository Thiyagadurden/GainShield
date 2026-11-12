# Controlled hardware-in-the-loop (HIL) roadmap

## Status ladder (honest)

| Stage | Status |
|---|---|
| Model-in-the-loop simulation (Python averaged model) | **Completed** (this repository) |
| Software-in-the-loop with the controller code compiled for the target | **Not started** – proposed |
| Processor-in-the-loop (PI + monitor on a C2000 MCU, plant on PC) | Proposed |
| Controller HIL (real MCU, real-time plant simulator) | Proposed |
| Low-voltage power HIL / scaled bench | Proposed (future) |
| Full-power hardware tests | Out of scope for this project |

No hardware validation has been performed.

## Proposed architecture

```
 [Real-time simulator: averaged AFE + DC link + DC-DC model, 10-20 us step]
        |  analog v_dc, i_d (±10 V)           ^  PWM duty / i_d* (digital or analog)
        v                                     |
 [Signal conditioning: scaling, anti-alias RC, galvanic isolation]
        |
 [Target MCU, e.g. TI C2000 F28379D: 10 kHz PI + anti-windup + runtime monitor + baseline fallback]
        |  UART/CAN (gain updates, audit records)       ^ gate-approved gains only
        v                                               |
 [Supervisory PC: GainShield optimiser + candidate gate + certificate + audit log + dashboard]
```

* **Split of responsibilities.** The 10 kHz loop, the monitor and the fallback run on the MCU (deterministic,
  independent of the PC). The GP optimiser, certificate checks and audit logging run on the PC; the MCU
  accepts only gain pairs that the PC gate approved **and** that pass a range check stored in MCU flash
  (a second, simpler copy of the certified box).
* **Real-time platform.** A Typhoon HIL-class or OPAL-RT-class simulator, or a university-owned equivalent.
  Typhoon HIL's offline simulator is free for academia, which allows model porting before buying hardware.
* **Sampling.** Plant step ≤ 20 µs (≥ 5× faster than the 100 µs control period); ADC sampling synchronised to
  the PWM carrier; measured total delay to be identified and compared with the 1.0–2.0-sample assumption.
* **I/O.** 2 analog inputs to the MCU (v_dc, i_d), 1 PWM or DAC channel back (i_d* or duty), 1 digital
  trip line, UART/CAN for supervision.
* **Protection.** Independent over/under-voltage trip on the simulator side; MCU watchdog; gain write
  protected by CRC + range check; fallback to baseline on communication loss; hardware OVP/UVP comparator
  (addresses failure case R5).

## Test cases and acceptance criteria

| # | Test | Acceptance criterion |
|---|---|---|
| H1 | Timing: PI + monitor execution on MCU | < 20 % of the 100 µs period, jitter < 2 µs |
| H2 | Delay identification | measured delay within 1.0–2.0 samples, else re-certify |
| H3 | Baseline on all 11 scenarios | voltage within ±5 %, matches simulation peak deviation within 15 % |
| H4 | GainShield gains (from simulation) | same as H3; no monitor alarm |
| H5 | Online tuning session (10 iterations) | zero episodes outside ±5 %, all decisions in audit log |
| H6 | Injected unstable gains (bypass) | rollback < 50 ms, no trip |
| H7 | Sensor faults (spike, stuck) | spike: alarm; stuck: hardware OVP/UVP trips safely |
| H8 | Communication loss PC↔MCU | MCU keeps / reverts to baseline within 1 control period |

Unsafe ablation configurations (B–F) are **never** run on hardware.

## Indicative budget and schedule

See `docs/COST_ESTIMATE.md` (PIL with a C2000 LaunchPad is low-cost; real-time HIL equipment is the major item
and should first be sought through institutional lab access).
