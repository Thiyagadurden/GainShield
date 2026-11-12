# Requirement traceability matrix

Status vocabulary: **Complete and tested** · **Implemented but not fully validated** · **Partially implemented** ·
**Not implemented**. "Complete" means code + automated test + generated evidence exist; it never means
hardware-validated.

## Deliverable 1 – Reproducible plant model, constraints, disturbance suite, manual PI baseline

| Requirement | Module | Test | Evidence | Status | Remaining work |
|---|---|---|---|---|---|
| Reproducible Python plant model (averaged AFE + DC link + DC-DC) | `plant/charger.py` | `test_plant.py` (equilibrium, energy balance, signs, delay) | MATHEMATICAL_MODEL.md §1 | Complete and tested | Switching-level model for HIL cross-check |
| Fixed voltage constraints (±5 % op., ±10 % trip) | `config/default.toml`, `evaluation/metrics.py` | `test_config.py`, `test_scenarios.py` | evaluation_runs.csv `v_viol_ms`, `v_trip` | Complete and tested | – |
| Fixed current constraints (80 A, 95 % threshold) | `plant/charger.py`, `controllers/pi.py`, `metrics.py` | `test_pi.py` (saturation) | `i_viol_ms`, `i_margin` | Complete and tested | – |
| Stability constraints (PM ≥ 40°, GM ≥ 6 dB, MM ≥ 0.5 worst case) | `stability/certify.py` | `test_stability.py` | certificate_summary.json | Complete and tested | – |
| Switching / sampling constraints (10 kHz, delay 1–2 samples) | `config`, `plant` delay line | `test_delay_line_resolution` | – | Complete and tested (as sampling + delay; switching ripple not modelled) | Switching ripple |
| Disturbance suite (10 classes, seeded) | `disturbances/scenarios.py` | `test_scenarios.py` | figures/eval_*.png | Complete and tested | – |
| Manually tuned PI baseline (documented procedure) | `controllers/baseline.py` | `test_symmetric_optimum_scaling`, certification test | MATHEMATICAL_MODEL.md §2 | Complete and tested | – |

## Deliverable 2 – Online gain tuning with bounded action space and stability/safety monitor

| Requirement | Module | Test | Evidence | Status | Remaining work |
|---|---|---|---|---|---|
| Bounded action space | `config [gains_box]`, tier-1/tier-2 masks, ×3 step limit | `test_proposals_stay_in_candidate_set` | tuning_history.csv | Complete and tested | – |
| Online PI tuning (closed-loop probe episodes on the plant) | `core.GainShield.tune_context` | `test_integration.py` | tuning_summary.json, gain_evolution.png | Complete and tested (in simulation) | Probe acceptability on a real charger |
| Safe Bayesian optimisation (GP surrogates, safe set, expanders) | `optimizer/gp.py`, `optimizer/safe_bo.py` | `test_optimizer.py` | safe_set_nominal.png; 0 of 482 tuning episodes outside ±5 % | Complete and tested (in simulation). Safety of learning is shown by test, not proven: the theoretical SafeOpt guarantee is not claimed | RKHS-bound analysis / more seeds |
| Context-aware (C, Vg, P, mode, τ_i, delay) | `simulation.ContextEstimate`, BO context inputs | integration + ablation E | ablation.csv | Implemented but not fully validated (context estimation is assumed, not implemented) | Online identification |
| Stability monitor (certificate re-check) | `safety/supervisor.CandidateGate` | `test_gate_rejects_and_accepts` | failure_injection.csv G1–G6 | Complete and tested | – |
| Safety monitor (runtime) | `safety/supervisor.RuntimeMonitor` | `test_monitor_*`, `test_*sensor*` | failure_injection.csv R1–R7 incl. R5/R5b (stuck sensor detected, virtual-sensor fallback) | Complete and tested (in simulation) | Threshold check on hardware noise (HIL H7) |

## Deliverable 3 – Safe fallback, rollback, complete audit log

| Requirement | Module | Test | Evidence | Status | Remaining work |
|---|---|---|---|---|---|
| Safe baseline controller always available | `core.SupervisedPIAgent` | integration test | – | Complete and tested | – |
| Automatic fallback on confidence/constraint failure | `GainShieldAgent._decide`, `_on_monitor` | `test_integration.py`, failure R1 | fault_unstable_gains.png | Complete and tested | – |
| Rollback with bumpless transfer and lock-out | `PIController.set_gains`, agent lock-out | `test_bumpless_transfer_output_continuous` | audit ROLLBACK records | Complete and tested | – |
| Log every gain change (prev/proposed/active, σ, margins, decision, reason) | `audit/logger.py` | `test_audit.py`, `verify_gain_trace` | results/audit/*.jsonl (0 trace problems) | Complete and tested | – |

## Deliverable 4 – Simulation dashboard

| Requirement | Module | Test | Evidence | Status | Remaining work |
|---|---|---|---|---|---|
| Voltage, current, power, mode | `dashboard/app.py` Monitoring | AppTest run (no exceptions) | – | Complete and tested (headless) | Hosted deployment |
| Gains, candidate, GP prediction/uncertainty, iteration | AI optimiser tab | AppTest | – | Complete and tested (headless) | – |
| Constraints, stability status, acceptance, margins, rollback | Safety tab | AppTest | – | Complete and tested (headless) | – |
| Experiment controls (scenario, duration, run baseline/GainShield, compare) | sidebar + Experiment tab | AppTest (scenario change) | – | Complete and tested (headless) | – |
| Audit panel (gain changes, rejections, rollback reasons, state history) | Audit tab | AppTest | – | Complete and tested (headless) | – |

## Deliverable 5 – Evaluation vs manual PI under identical conditions

| Metric | Where | Status |
|---|---|---|
| Settling time, overshoot (peak deviation + recovery overshoot), IAE | `evaluation/metrics.py`, `run_evaluation.py` | Complete and tested |
| Constraint violations (voltage, current, trips) | same | Complete and tested |
| Stability margin (true-plant PM/MM of every gain set used) | `run_evaluation.true_plant_margins` | Complete and tested |
| Computation time (per step, per decision, per BO iteration) | evaluation/tuning summaries | Complete (Python timing on one machine) |
| Robustness to model variation (C ±20 %, lag, delay) and sensor noise (×2, ×3) | scenario suite | Complete and tested |
| Performance during power reversal | g2v_to_v2g, v2g_to_g2v | Complete and tested |
| Identical conditions & multiple seeds, statistics | shared Scenario + pre-drawn noise; 5 seeds; Wilcoxon | Complete and tested |

## Deliverable 6 – Ablation, failure analysis, HIL roadmap

| Requirement | Module | Evidence | Status | Remaining work |
|---|---|---|---|---|
| Ablation A–F (+ B+C) | `run_ablation.py` | ablation.csv, ABLATION_REPORT.md | Complete and tested (simulation) | Larger budgets to stress B |
| Failure analysis (condition, root cause, detection, response, residual risk, mitigation) | `run_failure_injection.py`, `faults.py` | FAILURE_ANALYSIS.md | Complete and tested (simulation) | Implement mitigations |
| Controlled HIL roadmap | – | HIL_ROADMAP.md (staged plan, I/O, protection, 8 tests with acceptance criteria, costed) | Complete as a roadmap (the deliverable); no HIL performed yet | Execute PIL/HIL |
