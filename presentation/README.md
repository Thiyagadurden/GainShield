# Presentation

* `29727_TG10_Presentation_Round.pptx` – editable deck on the official TECHgium 10th Edition template (15 slides); the template prefix 00000 is replaced by 29727, the last 5 digits of PID TG0929727.
* `29727_TG10_Presentation_Round.pdf` – PDF export.
* `deck_figures.py` – regenerates the slide figures in the GainShield palette; `assets/` holds team photos, QR code and figures.
* `template_base15.pptx` – the official template with the Guidelines slide removed and the Technical Description
  (×2) and Validation / Testing / Analysis (×3) slides duplicated.
* `build_deck.py` – fills the template; every number is read from `results/` and `docs/RESULTS_SNAPSHOT.json`.

```bash
python presentation/deck_figures.py
python presentation/build_deck.py presentation/template_base15.pptx presentation/29727_TG10_Presentation_Round.pptx
```

Team, PID, college and repository details are filled in.

