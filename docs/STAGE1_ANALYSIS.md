# Stage 1 – document analysis

## 1. Official TECHgium template (`00000_TG10_Presentation_Round.pptx`)

* 16:9, 13.333 × 7.5 in; L&T Technology Services / TECHgium® 10th Edition branding.
* 13 slides: Cover (PID, concept title, 4 author photos + names, college) · Challenge Statement · Concept /
  Proposed Solution · Pros and Cons of the solution · Technical Description · Implementation Plan (×2) ·
  **Validation / Testing / Analysis** · Cost Estimate · Assumptions · References · Thank You · Guidelines.
* Content slides use layout `Text_Slide` (title 0.51,0.27 in; body 0.55,1.36 in, 12.29 × 5.18 in) with the
  TECHgium logo top-right and a blue→green→yellow vertical accent bar at the right edge; titles are dark,
  left-aligned with a grey rule.
* Guidelines (slide 13): max **15 slides**; no theoretical fundamentals; illustrate with drawings, examples,
  algorithms, infographics; consistent format, do not change the template; check spelling; highlight
  advantages over conventional techniques; rename file with the last 5 digits of the PID.

**"Bar Testing" / "Bar Analysis".** Neither heading appears in the official template. The only matching slide
is "Validation / Testing / Analysis"; the two headings in the brief are treated as a garbled rendering of it.
The official heading is preserved; the content is split into a test-protocol slide and a results-analysis
slide (both titled per the template). To be confirmed by the team.

## 2. Reference presentations (presentation quality only – content not reused)

| Technique observed | How GainShield uses it |
|---|---|
| Headline-sentence slide titles stating the takeaway | Sub-headline under each template title states the claim |
| Numbered markers guiding the eye through a process | Numbered pipeline in the concept and BO slides |
| KPI tiles with big numbers and a one-line label | Evaluation slide: measured improvements, violations, p-values |
| Phase timeline across the top | Implementation plan mapped to the six deliverables |
| Dense, aligned tables for cost and assumptions | Cost and assumptions slides |
| Source line under every number | "source: results/…" captions under charts |

Avoided: their purple / orange visual identities, decorative icon density, unsourced figures.

## 3. Missing information (and what was assumed)

| Missing | Handling |
|---|---|
| All numerical plant/constraint values | Engineering assumptions A-1…A-15 (ASSUMPTIONS.md), flagged on the Assumptions slide |
| PID number, team names/photos, college | Placeholders kept on the cover slide |
| GitHub URL | QR placeholder; generate with `qrcode` once published |
| Meaning of "Bar Testing/Analysis" | Interpreted as "Validation / Testing / Analysis" (see above) |

## 4. Requirements matrix

See `REQUIREMENTS_TRACEABILITY.md`.

## 5. Execution plan (as executed)

Stage 2 architecture → Stage 3 implementation with tests → Stage 4 experiments (certificate, tuning,
evaluation, failure injection, ablation) → Stage 5 docs and repository → Stage 6 slides from verified results →
Stage 7 audit.
