#!/usr/bin/env python3
"""
Script to run the LLM support tracker for all models.

MODEL_RELEASE_DATES is the source of truth for which models to track.
Outputs a single all_models.json file.
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
)


# MODEL_RELEASE_DATES is the source of truth for which models to track.
# Add new models here with their official release dates.
# Models are tracked even before they have index results or proxy support.
MODEL_RELEASE_DATES = {
    # Anthropic Claude models
    "claude-sonnet-4-5": "2025-09-29",
    "claude-sonnet-4-6": "2026-02-20",
    "claude-opus-4-5": "2025-11-24",
    "claude-opus-4-6": "2026-02-05",
    # Arcee AI models
    "trinity-large-thinking": "2026-04-01",
    # DeepSeek models
    "DeepSeek-V3.2-Reasoner": "2025-12-01",
    # GLM models (Z-AI/Zhipu)
    "GLM-4.7": "2025-10-01",
    "GLM-5": "2026-02-01",
    "GLM-5.1": "2026-04-10",
    # Google Gemini models
    "Gemini-3-Pro": "2025-11-18",
    "Gemini-3-Flash": "2025-12-17",
    "Gemini-3.1-Pro": "2026-03-04",
    # Moonshot Kimi models
    "Kimi-K2-Thinking": "2025-11-06",
    "Kimi-K2.5": "2026-01-27",
    # MiniMax models
    "MiniMax-M2.1": "2025-09-01",
    "MiniMax-M2.5": "2026-02-01",
    "MiniMax-M2.7": "2026-03-18",
    # NVIDIA Nemotron models
    "Nemotron-3-Nano": "2025-10-01",
    "Nemotron-3-Super": "2026-03-11",
    # OpenAI GPT models
    "GPT-5.2": "2025-12-11",
    "GPT-5.2-Codex": "2025-12-18",
    "GPT-5.4": "2026-03-05",
    # Alibaba Qwen models
    "Qwen3-Coder-480B": "2025-07-23",
    "Qwen3-Coder-Next": "2026-01-15",
    "Qwen3.6-Plus": "2026-04-01",
}


def main():
    # Use MODEL_RELEASE_DATES as the source of truth
    models = sorted(MODEL_RELEASE_DATES.keys())
    print(f"Tracking {len(models)} models from MODEL_RELEASE_DATES: {models}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Write directly to frontend/public - the single source of truth
    output_dir = os.path.join(os.path.dirname(script_dir), "frontend", "public")
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for model in models:
        print(f"\n{'='*60}")
        print(f"Processing: {model}")
        print("=" * 60)

        release_date = MODEL_RELEASE_DATES[model]

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

    # Write to frontend/public - single source of truth
    output_file = os.path.join(output_dir, "all_models.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Results written to {output_file}")
    print(f"Total models processed: {len(results)}")


if __name__ == "__main__":
    main()
