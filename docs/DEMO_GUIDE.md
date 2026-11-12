# Installation and live-demonstration guide

## Install (clean environment, CPU only)

```bash
git clone <repository-url> gainshield-safe-ev-charger-control
cd gainshield-safe-ev-charger-control
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                           # 36 tests, ~30 s
```

Python ≥ 3.11 (uses `tomllib`). No GPU, no MATLAB, no internet access needed after installation.

## Reproduce every result (~15 min on a laptop)

```bash
python experiments/run_all.py       # certificate -> tuning -> evaluation -> failures -> ablation -> reports
```

Or step by step: `run_certificate.py`, `run_tuning.py`, `run_evaluation.py`, `run_failure_injection.py`,
`run_ablation.py`, `make_reports.py`, and `python diagrams/make_diagrams.py`.

## Live demo script (≈ 6 minutes)

```bash
streamlit run dashboard/app.py
```

1. **Monitoring tab** – choose `g2v_to_v2g`, "Compare both", Run. Point at the voltage peak: baseline ≈ 22 V,
   GainShield ≈ 12 V, both inside the dashed ±5 % band; Kp trace shows the context-scheduled switch.
2. **AI optimiser tab** – the Kp–Ki map: grey crosses are not certified for this context, green squares are
   GP-safe *and* certified, the star is the deployed recommendation, the diamond is the baseline.
3. **Safety tab** – tier-1 / tier-2 certificate status and worst-case PM/GM/MM of the active gains;
   rollback / rejection records.
4. **Live tuning tab** – run 6 iterations at 10 kW: watch the safe set grow from the baseline; any
   rejection shows its reason.
5. **Audit tab** – every gain change with previous/proposed/active gains, GP σ, margins and reason;
   download the JSONL.
6. Close with `results/figures/fault_unstable_gains.png`: injected unstable gains are rolled back; without
   the monitor or fallback they oscillate.

## Troubleshooting

* "No trained model found": run `python experiments/run_tuning.py` (needs `results/certificate.npz`, created
  automatically).
* Slow first click in a new context: the tier-2 certificate for that context bin is being computed (~1.5 s),
  then cached.
