---
name: add-new-model
description: This skill should be used when adding a new LLM model to the support tracker, such as "add Gemini-3.1-Pro as a tier 1 model", "add a new model", "support a new LLM", or "add model aliases". Provides guidance on modifying track_llm_support.py to add new models with proper tier classification and aliases.
triggers:
- add model
- add new model
- tier 1 model
- model aliases
---

# Add New Model to LLM Support Tracker

This skill guides the process of adding a new language model to the OpenHands LLM Support Tracker.

## Overview

The LLM Support Tracker monitors when language models are supported across the OpenHands ecosystem. When adding a new model, update the configuration in `scripts/track_llm_support.py`.

## Key Components

### 1. TIER_1_PATTERNS

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

**When to modify**: Always add a new entry when supporting a new model. Include all known aliases for the model.

## Adding a New Model

### Step 1: Determine Model Tier

Check if the model should be tier 1 (priority) or tier 2:
- **Tier 1**: Major models from leading providers (Claude Sonnet/Opus, Gemini Pro/Flash, GPT-5*, GLM, Qwen3-Coder-*, MiniMax-M2.5, Kimi-K2.5)
- **Tier 2**: All other models

### Step 2: Check Tier Pattern Coverage

If adding a tier 1 model, verify the existing `TIER_1_PATTERNS` regex patterns. Only add a new pattern if no existing pattern matches the model ID.

### Step 3: Add to MODEL_ALIASES

Add an entry to `MODEL_ALIASES` with:
- **Key**: The canonical model ID (e.g., `"Gemini-3.1-Pro"`)
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

### Step 4: Add Tests

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

### Step 5: Run Tests

```bash
cd llm-support-tracker
pip install -r requirements.txt
pytest tests/ -v
```

## Validation Checklist

- [ ] Model ID follows canonical naming convention
- [ ] Tier 1 models are covered by `TIER_1_PATTERNS` regex
- [ ] `MODEL_ALIASES` entry includes all known aliases
- [ ] Tests added for tier classification
- [ ] Tests added for alias resolution
- [ ] All tests pass

## File Locations

- **Main script**: `scripts/track_llm_support.py`
- **Tests**: `tests/test_track_llm_support.py`
- **Dependencies**: `requirements.txt`
