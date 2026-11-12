# Mathematical model and stability certificate

## 1. Averaged plant (`gainshield/plant/charger.py`)

State x = [v, i_d, p_dc]: DC-link voltage [V], AFE d-axis grid current (peak, amplitude-invariant dq) [A],
power drawn from the link by the DC-DC stage [W].

```
C · v · dv/dt   = P_afe(i_d) − p_dc − v²/R                       (DC-link energy balance, W = ½Cv²)
P_ac            = 1.5 · V_g,pk · vg_pu · i_d                     (dq active power, unity PF, PLL locked)
P_afe           = η · P_ac   if P_ac ≥ 0    (rectifying, G2V)
                = P_ac / η   if P_ac < 0    (inverting,  V2G)
τ_i · di_d/dt   = i_d*(t − T_d) − i_d                            (closed inner current loop + delay)
τ_dc · dp_dc/dt = sat_slew(p_dem) − p_dc                         (DC-DC battery-power loop)
```

**Sign convention.** p_dc > 0: G2V, energy leaves the link to the battery. p_dc < 0: V2G. i_d > 0: power drawn
from the grid.

**Units check.** C·v·dv/dt: F·V·V/s = (C/V)·V²/s = W. ✓  P_ac: V·A = W. ✓

**Constant-power load.** The DC-DC stage regulates battery power independently of v, so p_dc does not depend
on v. Written in current form, i_dc = p_dc / v, the incremental conductance ∂i_dc/∂v = −p_dc/v² is negative
in G2V (the classic CPL negative-impedance effect, Emadi et al. 2006). In the energy form above the effect is
carried exactly by the 1/(C·v) factor.

**Numerics.** Fixed-step RK4 with 10 sub-steps per control period (h = 10 µs, ≥ 30 steps per τ_i,min).
The controller output is held (ZOH) and enters a delay line with 0.1-sample resolution.

**Verification (tests/test_plant.py).** Equilibrium is stationary; the change of stored energy equals the
integral of the power terms (energy conservation, 2 % tolerance over 4 ms open loop); sign conventions for G2V
/ V2G; delay-line timing; rejection of non-physical parameters.

## 2. Controller (`gainshield/controllers/pi.py`)

```
e[k] = Vref[k] − v_meas[k]
u[k] = sat( Kp·e[k] + x_I[k] ),      sat = ±80 A
x_I[k+1] = x_I[k] + Ki·Ts·e[k]       unless saturated and e drives further into saturation (clamping)
```

Bumpless gain change: `x_I ← u_prev − Kp_new · e_prev`, so the output is continuous at the switch instant.

**Manual baseline (symmetric optimum).** With G(s) = k / s · 1/(T_Σ s + 1),
k = 1.5·V_g,pk·η / (C·Vref) = 311 V/(A·s), T_Σ = τ_i + T_d + Ts/2 = 0.70 ms and a = 3.5:
Kp = 1/(a·T_Σ·k) = 1.311 A/V, Ki = Kp/(a²·T_Σ) = 152.9 A/(V·s).
Nominal PM 57.7°, GM 21.7 dB; worst case over U: PM 42.1°, GM 15.9 dB, MM 0.59 (certified).

## 3. Linearised discrete-time loop (`gainshield/stability/linear_model.py`)

Small-signal, lossless: dv/dt = k·i_d, di_d/dt = (u(t − T_d) − i_d)/τ_i, with T_d = (d_I + f)·Ts.
Exact ZOH discretisation with fractional input delay (Åström & Wittenmark):

```
x[k+1] = Φ x[k] + Γ0 u[k − d_I] + Γ1 u[k − d_I − 1]
P(z)   = k · N̂(z) / ((z − 1)(z − λ) z^(d_I+1)),     λ = e^(−Ts/τ_i)
C(z)   = Kp + Ki·Ts/(z − 1)
```

Every v-row entry of Φ, Γ0, Γ1 is proportional to k, hence the closed-loop characteristic polynomial is
**affine in k**:

```
p(z; k) = D(z) + k · N(z),    D = (z − 1)²(z − λ) z^(d_I+1),   N = N̂(z)·(Kp(z − 1) + Ki·Ts)
```

C (±20 %), grid voltage (0.8–1.1 pu) and direction-dependent efficiency enter only through
k ∈ [k_min, k_max] = [207.5, 445.7] V/(A·s).

**Validation of the linear model against the nonlinear plant** (`results/linear_vs_nonlinear.csv`): for five
(C, delay) combinations the critical gain multiplier predicted by the linear model separates stable (0.97×)
from unstable (1.03×) nonlinear simulations in every case.

## 4. Certificate (`gainshield/stability/certify.py`)

Four regions are kept distinct (figure `results/figures/kp_ki_regions.png`):

| region | definition | nature |
|---|---|---|
| Screened | spectral radius < 1 for 200 random plants from U | Monte-Carlo evidence |
| Nominal | spectral radius < 1 for the nominal plant | exact |
| Tier-1 robust | stable for **all** k in [k_min, k_max] at each of 88 (τ_i, delay) grid nodes | proof in k, grid in (τ_i, delay) |
| Certified (global) | tier-1 + worst PM ≥ 40°, GM ≥ 6 dB, MM ≥ 0.5 at k ∈ {k_min, k_nom, k_max} × 20 (τ_i, delay) nodes | proof + numerical margins |
| Empirically validated | no constraint violation in the nonlinear evaluation runs | evidence (results/evaluation_runs.csv) |

**Zero-exclusion argument (Barmish 1994).** For fixed (τ_i, delay), p(z; k) is stable for every k in the
segment iff it is stable at k_min and no k in the segment puts a root on |z| = 1. A unit-circle root
z = e^{jω} for real k requires Im{D(z)·conj N(z)} = 0; on the unit circle conj N(z) = N(1/z), so the candidate
frequencies are the unit-circle roots of the polynomial F(z) = D(z)·rev(N)(z) − rev(D)(z)·N(z). For each such
root k* = −D/N is evaluated; the segment is certified iff no real k* falls inside [k_min, k_max].
Implementation is checked against brute-force eigenvalue sweeps (400 random gain pairs × 400 k values: 100 %
agreement; unit test `test_zero_exclusion_matches_brute_force`).

**Tier 2 (context-conditioned).** At run time, the estimated context (C, Vg, τ_i, delay) and the estimation
error bounds (A-15) define a smaller set U(ctx) ⊂ U. Tier 2 requires local robust stability (same proof) and the
PM/GM/MM requirements over U(ctx). A gain applied by GainShield must satisfy **tier 1 (global) and tier 2
(local)**: tier 1 guarantees that a sudden context change inside U cannot destabilise the loop before the
supervisor re-decides; tier 2 allows higher gains when the context is known.

**Limitations.** Linear, small-signal (unsaturated) only; τ_i and delay gridded; R_loss neglected; LMI /
Lyapunov methods were considered but not needed for this single-input structured uncertainty (the affine-in-k
structure gives an exact test); they would become relevant for multi-parameter polytopic uncertainty.

## 5. Safe Bayesian optimisation (`gainshield/optimizer/`)

Inputs: x = (log-normalised Kp, Ki) ∈ [0,1]², context z = (C_pu, Vg_pu, P/P_rated, τ_i/τ_nom, delay/d_nom).
Three GPs (Matern-5/2, ARD): cost J, voltage margin m_v = (V_abort − max|e|)/V_abort, current margin m_i.
Margin GPs have zero prior mean (unexplored ⇒ unsafe) and fixed hyper-parameters.

```
S(z)  = { x ∈ X_c(z) : μ_m(x,z) − β σ_m(x,z) ≥ h  for m ∈ {m_v, m_i} } ∪ {baseline}
M(z)  = { x ∈ S : LCB_J(x) ≤ min_S UCB_J }
G(z)  = { x ∈ S : ∃ x' ∉ S with UCB_m(x) − L‖x − x'‖ ≥ h }
x_next = argmax_{M ∪ G} max(width_J / std(J), width_v, width_i)
recommend(z) = argmin_S UCB_J
```

with X_c(z) = tier-1 grid ∩ tier-2(z). This follows SafeOpt (Sui et al. 2015) and its contextual extension
(Berkenkamp, Krause, Schoellig 2023). The theoretical guarantee of those papers is **not** claimed (RKHS bound
unverified); safety rests on the certificate and the independent monitor.

Probe cost J = 0.35·IAE/IAE₀ + 0.25·peak_load_dev/·₀ + 0.10·OS/OS₀ + 0.10·t_s/t_s₀ + 0.20·ripple/ripple₀
(baseline-at-nominal normalisation; aborted episodes J ≥ 3).
