# References

Each entry was checked to exist (title, authors, venue) on 12 Nov 2026. The "used for" column says which
claim or design decision it supports.

| # | Reference | Used for |
|---|---|---|
| 1 | Y. Sui, A. Gotovos, J. W. Burdick, A. Krause, "Safe exploration for optimization with Gaussian processes," *ICML*, 2015. | SafeOpt safe set, maximisers/expanders, Lipschitz form |
| 2 | F. Berkenkamp, A. Krause, A. P. Schoellig, "Bayesian optimization with safety constraints: safe and automatic parameter tuning in robotics," *Machine Learning*, vol. 112, pp. 3713–3747, 2023, doi:10.1007/s10994-021-06019-1. | contextual safe BO, multiple constraints |
| 3 | C. König, M. Khosravi, M. Maier, R. S. Smith, A. Rupenyan, J. Lygeros, "Safety-aware cascade controller tuning using constrained Bayesian optimization," *IEEE Trans. Industrial Electronics*, doi:10.1109/TIE.2022.3158007 (arXiv:2010.15211). | BO for PI/PID tuning with stability-related constraints |
| 4 | C. König, M. Turchetta, J. Lygeros, A. Rupenyan, A. Krause, "Safe and efficient model-free adaptive control via Bayesian optimization," *IEEE ICRA*, 2021, doi:10.1109/ICRA48506.2021.9561349. | online adaptive gain tuning with safe BO |
| 5 | C. E. Rasmussen, C. K. I. Williams, *Gaussian Processes for Machine Learning*, MIT Press, 2006. | GP regression, Matern kernel |
| 6 | N. Srinivas, A. Krause, S. Kakade, M. Seeger, "Gaussian process optimization in the bandit setting: no regret and experimental design," *ICML*, 2010. | confidence bounds μ ± βσ |
| 7 | B. R. Barmish, *New Tools for Robustness of Linear Systems*, Macmillan, 1994. | zero-exclusion principle (tier-1 proof) |
| 8 | K. J. Åström, B. Wittenmark, *Computer-Controlled Systems*, 3rd ed., Prentice Hall, 1997. | ZOH discretisation with fractional delay |
| 9 | K. J. Åström, T. Hägglund, *Advanced PID Control*, ISA, 2006. | anti-windup, bumpless transfer |
| 10 | S. Preitl, R.-E. Precup, "An extension of tuning relations after symmetrical optimum method for PI and PID controllers," *Automatica*, vol. 35, no. 10, 1999. | manual baseline tuning |
| 11 | A. Emadi, A. Khaligh, C. H. Rivetta, G. A. Williamson, "Constant power loads and negative impedance instability in automotive systems," *IEEE Trans. Vehicular Technology*, vol. 55, no. 4, pp. 1112–1125, 2006. | CPL behaviour of the DC-DC stage |
| 12 | A. Yazdani, R. Iravani, *Voltage-Sourced Converters in Power Systems*, Wiley/IEEE Press, 2010. | dq power, DC-link energy balance, averaged VSC model |
| 13 | F. Pedregosa et al., "Scikit-learn: machine learning in Python," *JMLR*, vol. 12, pp. 2825–2830, 2011. | GP implementation |
| 14 | IEC 61851-23, *Electric vehicle conductive charging system – Part 23: DC electric vehicle supply equipment*. | context: DC charger requirements (not a compliance claim) |
| 15 | ISO 15118-20:2022, *Road vehicles – Vehicle to grid communication interface – Part 20*. | context: bidirectional power transfer (V2G) |
| 16 | IEEE Std 1547-2018, *Interconnection and interoperability of DER with electric power systems*. | context: grid-voltage ride-through considerations |
| 17 | Streamlit documentation, docs.streamlit.io (Community Cloud resource limits). | dashboard hosting cost |
| 18 | Typhoon HIL, "HIL101 real-time simulator" product page (MSRP $9,900, USA) and "TyphoonSim" (free for academia), typhoon-hil.com, accessed 12 Nov 2026. | HIL cost estimate |
| 19 | Arrow Electronics, LAUNCHXL-F28379D listing ($44.16), accessed 12 Nov 2026; TI SPRUI77 LaunchPad user's guide. | PIL cost, HIL roadmap |

Standards 14–16 are cited for context only; GainShield makes **no** compliance claim.
