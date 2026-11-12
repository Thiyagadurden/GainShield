# Technical limitations and remaining work

## Limitations (known, documented)

1. **Simulation only.** Averaged model; no SIL on target, no HIL, no hardware. All numbers are model-based.
2. **Assumed parameters.** The problem statement gives no numbers; all are assumptions (ASSUMPTIONS.md).
3. **Certificate scope.** Linear, small-signal; proof over the k-interval, grid over τ_i × delay; does not
   cover current saturation, CPL large-signal effects (checked empirically) or plants outside U.
4. **GP safety is not a guarantee.** The SafeOpt regularity assumption (RKHS bound) is not verified; GP
   predictions are one layer of three.
5. **Context estimation is assumed.** C, τ_i and delay are taken as identified within the bounds of A-15;
   no estimator is implemented. A wrong context outside those bounds weakens tier 2 (tier 1 still holds
   inside U).
6. **Stuck voltage sensor is not detected** (failure case R5). Mitigation proposed, not implemented.
7. **Decision latency.** Uncached tier-2 certification ≈ 1.5 s in Python per new context bin; acceptable in
   a supervisory PC, not on an MCU. Needs an offline lookup table over a context grid.
8. **Conservatism.** The improvement is bounded (≈15 % mean peak-deviation/IAE) because every gain must be
   robustly stable for the whole uncertainty set and backed by GP evidence; ablation C shows more
   performance is available at the cost of evidence.
9. **Trade-off.** Higher gains increase sensor-noise amplification (current-reference ripple +8 % on average).
10. **Cost weights and probe design** are design choices without a sensitivity study.
11. **Evaluation size.** 11 scenarios × 5 seeds; no hardware variability.

## Remaining work (prioritised)

| Priority | Item | Deliverable affected |
|---|---|---|
| 1 | Power-balance observer for sensor-fault detection (R5) | 3, 6 |
| 2 | Pre-computed tier-2 lookup table; port PI + monitor to C (MCU) | 2, 6 |
| 3 | Online capacitance / delay identification | 2 |
| 4 | PIL on C2000 LaunchPad, then controller-HIL (HIL_ROADMAP.md) | 6 |
| 5 | Cost-weight sensitivity study; more seeds; sweep of probe amplitude | 5 |
| 6 | Earlier oscillation detection (growth-rate detector) | 3 |
| 7 | Extend to the inner current loop gains (joint tuning) | 2 |
