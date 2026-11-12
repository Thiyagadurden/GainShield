# Presentation

* `GainShield_TECHgium_00000.pptx` – editable deck on the official TECHgium 10th Edition template (15 slides).
  Rename `00000` to the last 5 digits of your PID before uploading (template guideline).
* `GainShield_TECHgium_00000.pdf` – PDF export.
* `template_base15.pptx` – the official template with the Guidelines slide removed and the Technical Description
  (×2) and Validation / Testing / Analysis (×3) slides duplicated.
* `build_deck.py` – fills the template; every number is read from `results/` and `docs/RESULTS_SNAPSHOT.json`.

```bash
python presentation/build_deck.py presentation/template_base15.pptx presentation/GainShield_TECHgium_00000.pptx
```

Still to fill in by the team: PID, four photos and names, college/city/state (cover), GitHub QR code (slide 8).
