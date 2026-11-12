# Cost estimate (INR)

Prices researched **12 Nov 2026**. Exchange rate used: **1 USD ≈ ₹94** (mid-market ≈ 93.9 on 8 Nov 2026,
currencybeacon.com; RBI/PTI reports 93.7–94.5 in early Nov 2026). Foreign list prices exclude Indian import
duty and GST; budgetary only. **No vendor quotation has been requested and no partnership exists.**

## A. Actual cost of the delivered prototype (simulation)

| Item | Cost | Note |
|---|---|---|
| Software stack (Python, NumPy, SciPy, scikit-learn, pandas, Matplotlib, Plotly, Streamlit, pytest) | ₹0 | open-source |
| Computing | ₹0 | runs on a 2-core CPU: certificate ≈ 20 s, tuning ≈ 1.5 min, full evaluation ≈ 2.5 min; **no GPU needed** |
| Cloud resources | ₹0 | none required |
| Storage / version control | ₹0 | GitHub free tier (repository < 50 MB) |
| Dashboard hosting | ₹0 | Streamlit Community Cloud free tier (public apps; ~1 GB memory, sleeps when idle) |
| MATLAB/Simulink | ₹0 | not used (Python model chosen for reproducibility); optional student suite ≈ $119/yr ≈ ₹11,200 if desired |
| **Total cash spent** | **₹0** | |
| Team effort (in kind) | ≈ 4 people × 8 weeks × 15 h = 480 h | at an assumed ₹300/h intern-equivalent ≈ ₹1.44 lakh (not a cash cost) |

## B. Estimated cost of the next phase (PIL + low-cost validation)

| Item | Qty | Unit (source) | INR |
|---|---|---|---|
| TI LAUNCHXL-F28379D C2000 LaunchPad | 2 | $44.16 (Arrow) – ₹5,712 (Indian distributor) | ₹8,300 – ₹11,400 |
| Signal conditioning, isolation, cables, enclosure | 1 | engineering estimate | ₹6,000 – ₹10,000 |
| **Subtotal** | | | **≈ ₹15,000 – ₹22,000** |

## C. Optional future costs (HIL and hardware validation)

| Item | Basis | INR (indicative) |
|---|---|---|
| Real-time HIL – institutional lab access | many Indian institutes own HIL/RT simulators | ₹0 – ₹50,000 (usage charges, if any) |
| Real-time HIL – entry teaching kit (Typhoon HIL101) | US MSRP $9,900; APAC price differs | ≈ ₹9.3 lakh + duties/GST |
| Real-time HIL – research-grade (HIL404 class) | a published 2025 commercial quote totalled $44,000 incl. licences | ≈ ₹41 lakh (indicative only) |
| Offline real-time model preparation (TyphoonSim) | free for academia | ₹0 |
| Scaled low-voltage bidirectional converter bench (e.g. 48 V / 1 kW) | engineering estimate, not quoted | ₹1.5 – ₹3 lakh |

**Recommended path:** A (done, ₹0) → B (≈ ₹20k) → C via institutional HIL access before any purchase.
