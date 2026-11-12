# Ablation study

*Generated from `results/ablation.csv` by `experiments/make_reports.py`. Isolated simulation only - the
unsafe variants must never be connected to hardware.*

Each variant is trained from scratch on the same 13 contexts with the same seeds and 20 iterations per context,
then (i) deployed on 7 evaluation scenarios × 2 seeds (performance relative to the baseline on the same runs),
and (ii) subjected to the same fault: unstable gains (Kp = 0.30, Ki = 1500) written behind the gate at 60 ms.

## Results

| variant | episodes | rejected | tuning_monitor_aborts | tuning_unsafe_episodes | tuning_not_robustly_stable_gains | tuning_max_dev_V | deploy_peak_dev_vs_baseline | deploy_IAE_vs_baseline | deploy_ripple_vs_baseline | deploy_trips | fault_detected | fault_rolled_back | fault_peak_dev_pct | fault_v_viol_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A complete | 233 | 42 | 0 | 0 | 0 | 18.7 | 0.796 | 0.818 | 1.18 | 0 | True | True | 3.95 | 0 |
| B no certified region | 227 | 48 | 0 | 0 | 2 | 14.3 | 0.856 | 0.842 | 1.07 | 0 | True | True | 3.95 | 0 |
| C no GP uncertainty | 35 | 240 | 0 | 0 | 0 | 18.6 | 0.692 | 0.68 | 1.34 | 0 | True | True | 4.71 | 0 |
| D no runtime monitor | 233 | 42 | 0 | 0 | 0 | 18.7 | 0.796 | 0.818 | 1.18 | 0 | False | False | 7.54 | 47.5 |
| E no context | 245 | 30 | 0 | 0 | 0 | 18.6 | 0.886 | 0.969 | 1.18 | 0 | True | True | 4.69 | 0 |
| F no fallback | 233 | 42 | 0 | 0 | 0 | 18.7 | 0.796 | 0.818 | 1.18 | 0 | True | False | 7.54 | 47.5 |
| B+C plain constrained BO | 22 | 253 | 0 | 0 | 1 | 18.2 | 0.944 | 0.928 | 1.06 | 0 | True | True | 4.13 | 0 |

## What each ablation removes and what it demonstrates

| variant | what was removed | why it matters | safety risk |
|---|---|---|---|
| A complete | nothing | reference | - |
| B no certified region | candidate set = whole Kp-Ki box; gate skips the certificate | the certificate is the only layer that is valid for EVERY plant in U without testing | gains with no stability proof can reach the plant; safety then rests on GP regularity assumptions |
| C no GP uncertainty | safe set and gate use the GP mean only (beta = 0, no sigma check) | sigma is what stops the optimiser trusting extrapolations | deployed gains are supported by extrapolation, not by measured episodes |
| D no runtime monitor | monitor disabled | the monitor is the only layer that sees the real signals | faults outside the model (corrupted gains, plant drift) go undetected |
| E no context | context features constant; only the global certificate | optimal gains depend on C, Vg, P, mode | one compromise gain set for all conditions |
| F no fallback | alarms are raised but nothing is rolled back | detection without action does not protect | a detected instability persists |
| B+C plain constrained BO | both B and C removed | closest to 'ordinary BO with a constraint model' | combined risk of B and C |

## Reading the results honestly

* **D (no monitor) and F (no fallback)** are the clearest: under the injected fault the complete system
  detects the excursion and rolls back (peak ≈ 4 %, no time outside ±5 %), whereas D and F let a sustained
  limit-cycle oscillation persist (peak ≈ 7.5 %, tens of ms outside the band). In normal operation D and F
  behave exactly like A - these layers cost nothing until something goes wrong.
* **B (no certified region)**: within this iteration budget the local, step-limited GP expansion did not
  reach unstable gains, so no unsafe episode occurred. The certificate's value is therefore not visible in
  these averages: it is a *guarantee* (every gain ever applied is provably stable for every plant in U),
  not a statistical improvement. B did apply more gains that miss the global worst-case margins.
* **C (no GP uncertainty)** looks *better* on deployed performance because it trusts GP-mean extrapolations
  into aggressive gains after only a handful of measured episodes (most of its proposals were rejected by
  the gain-step limit). Those deployed gains are certified (the gate still re-checks stability) but are
  not backed by measured episodes; this is precisely the behaviour the sigma check is meant to prevent.
  It also shows the full system is conservative and leaves performance on the table.
* **The gain-step limit is an additional, non-ablated gate check.** In C and B+C most proposals
  (>150 of ~170) were rejected because the optimiser, trusting GP means, jumped more than ×3 away from the
  active gains. This is why no unsafe episode occurred even in B+C: the remaining layers caught it.
* **E (no context)** loses part of the improvement because it must use the global certificate and one
  compromise model for all operating points.
