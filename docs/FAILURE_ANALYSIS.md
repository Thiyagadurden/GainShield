# Failure analysis

*Generated from `results/failure_injection.csv` (script `experiments/run_failure_injection.py`).
All cases are deliberate fault injections in simulation.*

| case | root cause | detection | observed response | detected | peak dev % | trip | residual risk | proposed mitigation |
|---|---|---|---|---|---|---|---|---|
| G1 candidate outside certified region | optimizer bug or exploration outside the certified set | candidate gate: exact tier-1/tier-2 re-check | rejected, baseline kept | True | – | 0 | none (rejected before application) | keep exact re-check independent of optimizer code |
| G2 certified gains but GP margin uncertainty high | GP extrapolating into an unexplored region | gate: sigma threshold | rejected, baseline kept | True | – | 0 | none | - |
| G3 certified gains but GP margin lower bound below threshold | GP predicts insufficient margin | gate: lower confidence bound | rejected, baseline kept | True | – | 0 | none | - |
| G4 context outside validated envelope (C = 0.6 pu) | plant outside the modelled uncertainty set (e.g. failed capacitor) | gate: context envelope | rejected, baseline kept | True | – | 0 | baseline itself is not certified outside U | capacitance estimation + protection trip |
| G5 excessive gain step (x5 Kp) | large jump in gains | gate: step limit (x3) + certificate | rejected, baseline kept | True | – | 0 | none | - |
| G6 valid candidate (control case) | control case | - | accepted | False | – | 0 | - | - |
| R1 unstable gains injected at 60 ms (gate bypassed) | unstable gains reach the PI (corrupted write / software fault) | runtime monitor: voltage abort band | rollback to baseline | True | 3.95 | 0 | ~45 ms of growing oscillation before the 4 % abort band is hit | add a growth-rate detector to catch oscillation earlier |
| R2 same, runtime monitor disabled (ablation D) | same, monitor disabled | none | none | False | 7.56 | 0 | sustained limit cycle; would rely on hardware protection | never disable the monitor |
| R3 same, fallback disabled (ablation F) | same, fallback disabled | alarm only | alarm only (fallback disabled) | True | 7.56 | 0 | sustained limit cycle | fallback must be unconditional |
| R4 voltage-sensor spike +60 V for 0.3 ms | voltage-sensor spike (EMI) | monitor: implausible dV per sample | rollback to baseline | True | 0.795 | 0 | baseline briefly sees the spike | median filtering of the measurement |
| R5 voltage sensor stuck at 800 V from 100 ms, load step at 150 ms | voltage sensor stuck | NOT DETECTED by the current monitor | none | False | 96.3 | 1 | loss of regulation, trip (shown in table) | analytical redundancy: power-balance observer comparing predicted and measured v_dc; independent hardware OVP/UVP comparator |
| R6 plant outside model: C = 0.5 pu, delay 3 samples (context not updated) | plant drift outside U with stale context (C = 0.5, delay 3) | not detected (response stayed acceptable) | none | False | 1.87 | 0 | no guarantee outside U | online C estimation; envelope check on estimated context |
| R7 overload: 30 kW step at 0.80 pu grid (current limit) | overload: 30 kW at 0.8 pu grid | monitor: current-limit hold | alarm, baseline already active | True | 3.29 | 0 | alarm only, baseline already active | power derating / DC-DC current limit coordination |
| R6-ref baseline only, plant outside model | plant drift outside U with stale context (C = 0.5, delay 3) | not detected (response stayed acceptable) | – | – | 1.87 | 0 | no guarantee outside U | online C estimation; envelope check on estimated context |
| R7-ref baseline only, overload | overload: 30 kW at 0.8 pu grid | monitor: current-limit hold | – | – | 3.29 | 0 | alarm only, baseline already active | power derating / DC-DC current limit coordination |

## Findings

1. Every unsafe **proposal** in G1-G5 is rejected by the gate with an explicit, logged reason.
2. An unstable gain set that bypasses the gate (R1) is caught by the runtime monitor and rolled back to
   the baseline; without the monitor (R2) or the fallback (R3) the oscillation persists.
3. **Known gap (R5):** a *stuck* voltage sensor is not detected by the current monitor - it only looks at
   the measured voltage and its rate of change. The baseline PI is equally blind to it. This is a real
   residual risk and is listed in LIMITATIONS.md with the proposed mitigation (power-balance observer +
   independent hardware over/under-voltage protection).
4. Outside the modelled uncertainty set (R6) GainShield gives no guarantee; in this case the response
   remained acceptable, but that is an observation, not a claim.
5. During evaluation the oscillation detector raised false alarms on the baseline under 2× sensor noise;
   it was changed to run on a 0.5 ms low-pass-filtered error with 4 V hysteresis. The remaining alarms in
   the `combined` scenario are genuine excursions beyond the 4 % abort band while the baseline was active.
