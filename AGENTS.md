# AGENTS.md

## Repo notes
- Python tracker logic lives in `scripts/track_llm_support.py`.
- `scripts/run_all_models.py` is the source of truth for tracked models via `MODEL_RELEASE_DATES`.
- Canonical tracker model IDs should be slash-free because index-results matching looks for `results/<model_id>/scores.json`.
- Cross-system names belong in `MODEL_ALIASES`; use aliases for frontend names, LiteLLM/OpenRouter names, and other exact spellings.
- Tier 1 classification is controlled by `TIER_1_PATTERNS` in `scripts/track_llm_support.py`.

## Validation
- Install deps with `python -m pip install -r requirements.txt`.
- Run tracker tests with `GIT_TERMINAL_PROMPT=0 python -m pytest tests/test_track_llm_support.py -q` to avoid interactive git credential prompts during tests.
