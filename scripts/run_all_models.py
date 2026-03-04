#!/usr/bin/env python3
"""
Script to run the LLM support tracker for all models in openhands-index-results.

Outputs a single all_models.json file as the source of truth.
"""

import json
import os
import sys

# Add parent directory to path so we can import track_llm_support
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from track_llm_support import (
    track_llm_support,
    cleanup_litellm_cache,
    cleanup_infra_cache,
    cleanup_sdk_cache,
    cleanup_frontend_cache,
    cleanup_index_results_cache,
    _get_index_results_repo,
)


# Release dates for known models (verified from official sources)
MODEL_RELEASE_DATES = {
    # DeepSeek models
    "DeepSeek-V3.2-Reasoner": "2025-12-01",
    # GLM models (Z-AI/Zhipu)
    "GLM-4.7": "2025-10-01",
    "GLM-5": "2026-02-01",
    # OpenAI GPT models
    "GPT-5.2-Codex": "2025-12-18",
    "GPT-5.2": "2025-12-11",
    # Google Gemini models
    "Gemini-3-Flash": "2025-12-17",
    "Gemini-3-Pro": "2025-11-18",
    # Moonshot Kimi models
    "Kimi-K2-Thinking": "2025-11-06",
    "Kimi-K2.5": "2026-01-27",
    # MiniMax models
    "MiniMax-M2.1": "2025-09-01",
    "MiniMax-M2.5": "2026-02-01",
    # NVIDIA Nemotron models
    "Nemotron-3-Nano": "2025-10-01",
    # Alibaba Qwen models
    "Qwen3-Coder-480B": "2025-12-01",
    "Qwen3-Coder-Next": "2026-01-15",
    # Anthropic Claude models
    "claude-opus-4-5": "2025-11-24",
    "claude-opus-4-6": "2026-02-05",
    "claude-sonnet-4-5": "2025-09-29",
    "claude-sonnet-4-6": "2026-02-20",
}


def get_models_from_index_results() -> list[str]:
    """Get list of model folders from openhands-index-results using local git clone."""
    try:
        cache = _get_index_results_repo()
        temp_dir = cache["temp_dir"]
        
        results_dir = os.path.join(temp_dir, "results")
        if not os.path.exists(results_dir):
            print("No results directory found!")
            return []
        
        models = []
        for name in os.listdir(results_dir):
            if os.path.isdir(os.path.join(results_dir, name)):
                models.append(name)
        
        return sorted(models)
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []


def main():
    print("Fetching models from openhands-index-results...")
    models = get_models_from_index_results()

    if not models:
        print("No models found!")
        sys.exit(1)

    print(f"Found {len(models)} models: {models}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), "data")
    os.makedirs(data_dir, exist_ok=True)

    results = []
    for model in models:
        print(f"\n{'='*60}")
        print(f"Processing: {model}")
        print("=" * 60)

        # Get release date (use default if not known)
        release_date = MODEL_RELEASE_DATES.get(model, "2025-01-01")

        try:
            result = track_llm_support(model, release_date)
            results.append(result)
            print(f"\nResult: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"Error processing {model}: {e}")

    # Clean up all caches
    cleanup_sdk_cache()
    cleanup_frontend_cache()
    cleanup_index_results_cache()
    cleanup_litellm_cache()
    cleanup_infra_cache()

    # Write single source of truth
    output_file = os.path.join(data_dir, "all_models.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Results written to {output_file}")
    print(f"Total models processed: {len(results)}")


if __name__ == "__main__":
    main()
