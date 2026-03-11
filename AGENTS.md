# Repository Notes

- Install Python deps with `python -m pip install -r requirements.txt`.
- Run tests with `python -m pytest tests/`.
- `frontend/public/all_models.json` is the generated data source consumed by the frontend.
- `scripts/run_all_models.py` regenerates `frontend/public/all_models.json` from tracker logic.
- `frontend_support_timestamp` means the model was added to OpenHands/OpenHands frontend (`verified-models.ts`).
- `frontend_saas_available` is a separate signal for current app.all-hands.dev SaaS availability.
