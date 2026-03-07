---
name: add-new-model
description: This skill should be used when adding a new LLM model to the support tracker, such as "add Gemini-3.1-Pro as a tier 1 model", "add a new model", "support a new LLM", or "add model aliases". Provides guidance on modifying track_llm_support.py to add new models with proper tier classification and aliases.
triggers:
- add model
- add new model
- tier 1 model
- model aliases
- saas model
- verified model
---

# Add New Model to LLM Support Tracker

This skill guides the process of adding a new language model to the OpenHands LLM Support Tracker.

## Overview

The LLM Support Tracker monitors when language models are supported across the OpenHands ecosystem. Adding a new model requires updating:

1. `scripts/run_all_models.py` - Add the model to `MODEL_RELEASE_DATES` (required)
2. `scripts/track_llm_support.py` - Add aliases to `MODEL_ALIASES` (if needed)
3. **SaaS Database** - Add the model via Admin API for app.all-hands.dev availability (see below)

## Key Components

### 1. MODEL_RELEASE_DATES (Source of Truth)

Located in `scripts/run_all_models.py`, this dictionary is **the source of truth** for which models to track:

```python
MODEL_RELEASE_DATES = {
    # Anthropic Claude models
    "claude-sonnet-4-5": "2025-09-29",
    "claude-opus-4-6": "2026-02-05",
    # Google Gemini models
    "Gemini-3-Pro": "2025-11-18",
    "Gemini-3.1-Pro": "2026-03-04",
    # OpenAI GPT models
    "GPT-5.2": "2025-12-11",
    "GPT-5.4": "2026-03-05",
    # ... more models
}
```

**When to modify**: Always add new models here with their official release date. Models are tracked immediately even before they have index results or proxy support.

### 2. TIER_1_PATTERNS

Located at the top of `track_llm_support.py`, this list defines regex patterns for tier 1 (priority) models:

```python
TIER_1_PATTERNS = [
    r"^claude-sonnet-",      # Claude Sonnet
    r"^claude-opus-",        # Claude Opus
    r"^Gemini-.*-Pro$",      # Gemini Pro
    r"^Gemini-.*-Flash$",    # Gemini Flash
    r"^GPT-5",               # GPT-5*
    r"^GLM-",                # GLM
    r"^Qwen3-Coder-",        # Qwen3-Coder-*
    r"^MiniMax-M2\.5$",      # MiniMax-M2.5 only
    r"^Kimi-K2\.5$",         # Kimi-K2.5 only
]
```

**When to modify**: Only add a new pattern if the existing patterns don't cover the new model. For example, `Gemini-3.1-Pro` is already covered by `r"^Gemini-.*-Pro$"`.

### 2. MODEL_ALIASES

This dictionary maps canonical model IDs to their known aliases across different systems (frontend, SDK, LiteLLM, proxy configs):

```python
MODEL_ALIASES: dict[str, list[str]] = {
    "Gemini-3-Pro": [
        "gemini-3-pro-preview",  # Frontend verified-models.ts
        "gemini-3-pro",
    ],
    # ... more models
}
```

**When to modify**: Add aliases when the model uses different names across systems (frontend, SDK, LiteLLM, proxy).

## Adding a New Model

### Step 1: Add to MODEL_RELEASE_DATES (Required)

Add the model to `MODEL_RELEASE_DATES` in `scripts/run_all_models.py` with its official release date:

```python
MODEL_RELEASE_DATES = {
    # ... existing models ...
    "New-Model-Name": "2026-03-15",  # Official release date
}
```

This is **required** - the model won't be tracked without this entry.

### Step 2: Determine Model Tier

Check if the model should be tier 1 (priority) or tier 2:
- **Tier 1**: Major models from leading providers (Claude Sonnet/Opus, Gemini Pro/Flash, GPT-5*, GLM, Qwen3-Coder-*, MiniMax-M2.5, Kimi-K2.5)
- **Tier 2**: All other models

### Step 3: Check Tier Pattern Coverage

If adding a tier 1 model, verify the existing `TIER_1_PATTERNS` regex patterns in `scripts/track_llm_support.py`. Only add a new pattern if no existing pattern matches the model ID.

### Step 4: Add to MODEL_ALIASES (If Needed)

If the model uses different names across systems, add an entry to `MODEL_ALIASES` in `scripts/track_llm_support.py`:
- **Key**: The canonical model ID (must match the key in `MODEL_RELEASE_DATES`)
- **Value**: List of aliases used across different systems:
  - Frontend `verified-models.ts` names
  - LiteLLM naming conventions (e.g., `provider/model-name`)
  - Lowercase variants

Example:

```python
"Gemini-3.1-Pro": [
    "gemini-3.1-pro-preview",  # Frontend verified-models.ts
    "gemini-3.1-pro",
    "gemini/gemini-3.1-pro",   # LiteLLM naming
],
```

### Step 5: Add Tests

Add test cases to `tests/test_track_llm_support.py`:

1. **Tier test**: Verify the model tier in `TestGetModelTier`:
   ```python
   def test_gemini_31_pro_is_tier_1(self):
       """Gemini-3.1-Pro should be tier 1."""
       assert get_model_tier("Gemini-3.1-Pro") == 1
   ```

2. **Alias test**: Verify aliases in `TestModelAliases`:
   ```python
   def test_gemini_31_has_preview_alias(self):
       """Gemini-3.1-Pro should have -preview suffix alias."""
       aliases = get_model_aliases("Gemini-3.1-Pro")
       assert "gemini-3.1-pro-preview" in aliases
   ```

### Step 6: Run Tests

```bash
cd llm-support-tracker
pip install -r requirements.txt
pytest tests/ -v
```

## Adding Model to SaaS Database (app.all-hands.dev)

After [PR OpenHands/OpenHands#12833](https://github.com/OpenHands/OpenHands/pull/12833), OpenHands SaaS loads verified models from a database instead of the hardcoded `verified-models.ts` file. Models must be added to this database to appear in the app.all-hands.dev model dropdown.

### Admin API Endpoints

The SaaS admin API is at `https://app.all-hands.dev/api/admin/verified-models`. **Requires admin authentication** (users with `@all-hands.dev` email domain).

#### Create a Verified Model

```bash
curl -X POST "https://app.all-hands.dev/api/admin/verified-models" \
  -H "Authorization: Bearer $OPENHANDS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "claude-opus-4-6",
    "provider": "openhands",
    "is_enabled": true
  }'
```

**Request Body:**
- `model_name` (string, required): The model name (max 255 chars)
- `provider` (string, required): The provider name, typically `"openhands"` (max 100 chars)
- `is_enabled` (boolean, optional): Whether the model is enabled in the dropdown (default: `true`)

**Response (201 Created):**
```json
{
  "id": 42,
  "model_name": "claude-opus-4-6",
  "provider": "openhands",
  "is_enabled": true,
  "created_at": "2026-03-07T18:00:00Z",
  "updated_at": "2026-03-07T18:00:00Z"
}
```

#### List Verified Models

```bash
curl "https://app.all-hands.dev/api/admin/verified-models" \
  -H "Authorization: Bearer $OPENHANDS_API_KEY"
```

Optional query parameters:
- `provider`: Filter by provider (e.g., `?provider=openhands`)
- `limit`: Max results per page (default: 100, max: 100)
- `page_id`: Pagination cursor from previous response

#### Update a Verified Model

```bash
curl -X PUT "https://app.all-hands.dev/api/admin/verified-models/openhands/claude-opus-4-6" \
  -H "Authorization: Bearer $OPENHANDS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": false}'
```

#### Delete a Verified Model

```bash
curl -X DELETE "https://app.all-hands.dev/api/admin/verified-models/openhands/claude-opus-4-6" \
  -H "Authorization: Bearer $OPENHANDS_API_KEY"
```

### Checking SaaS Availability

The tracker checks if a model is in the SaaS database via the public models API:
```bash
curl "https://app.all-hands.dev/api/options/models" \
  -H "Authorization: Bearer $LLM_API_KEY"
```

Models appear as `openhands/model-name` in the response when available.

### Important Notes

1. **Both required for full frontend support**: A model needs to be in BOTH:
   - `verified-models.ts` (for self-hosted OpenHands)
   - SaaS `verified_models` database (for app.all-hands.dev)

2. **The tracker's `frontend_support_timestamp`** is only set when a model is available in both places.

3. **The tracker's `frontend_saas_available`** field indicates whether a model is currently in the SaaS database.

## Validation Checklist

- [ ] Model added to `MODEL_RELEASE_DATES` with correct release date
- [ ] Model ID follows canonical naming convention
- [ ] Tier 1 models are covered by `TIER_1_PATTERNS` regex
- [ ] `MODEL_ALIASES` entry includes all known aliases (if needed)
- [ ] Tests added for tier classification
- [ ] Tests added for alias resolution (if aliases added)
- [ ] All tests pass
- [ ] Model added to SaaS database via Admin API (for app.all-hands.dev availability)

## File Locations

- **Model registry (source of truth)**: `scripts/run_all_models.py` - `MODEL_RELEASE_DATES`
- **Tier patterns & aliases**: `scripts/track_llm_support.py`
- **Tests**: `tests/test_track_llm_support.py`
- **Dependencies**: `requirements.txt`
- **SaaS Admin API**: `https://app.all-hands.dev/api/admin/verified-models` (OpenHands repo: `enterprise/server/verified_models/`)
