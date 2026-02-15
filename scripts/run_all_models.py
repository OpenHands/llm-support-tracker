#!/usr/bin/env python3
"""
Script to run the LLM support tracker for all models in openhands-index-results.
"""

import json
import os
import subprocess
import sys

import requests


GITHUB_API_BASE = "https://api.github.com"
INDEX_RESULTS_REPO = "OpenHands/openhands-index-results"

# Approximate release dates for known models (can be updated)
MODEL_RELEASE_DATES = {
    "DeepSeek-V3.2-Reasoner": "2025-12-01",
    "GLM-4.7": "2025-10-01",
    "GPT-5.2-Codex": "2025-09-01",
    "GPT-5.2": "2025-08-01",
    "Gemini-3-Flash": "2025-11-01",
    "Gemini-3-Pro": "2025-11-01",
    "Kimi-K2-Thinking": "2025-10-01",
    "Kimi-K2.5": "2025-11-01",
    "MiniMax-M2.1": "2025-09-01",
    "MiniMax-M2.5": "2025-11-01",
    "Nemotron-3-Nano": "2025-10-01",
    "Qwen3-Coder-480B": "2025-12-01",
    "claude-opus-4-5": "2025-11-01",
    "claude-opus-4-6": "2025-12-01",
    "claude-sonnet-4-5": "2025-09-29",
}


def get_github_headers() -> dict:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_models_from_index_results() -> list[str]:
    """Get list of model folders from openhands-index-results."""
    headers = get_github_headers()
    url = f"{GITHUB_API_BASE}/repos/{INDEX_RESULTS_REPO}/contents/results"

    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code != 200:
        print(f"Error fetching models: {response.status_code}")
        return []

    contents = response.json()
    models = []
    for item in contents:
        if item.get("type") == "dir":
            models.append(item.get("name"))

    return models


def main():
    print("Fetching models from openhands-index-results...")
    models = get_models_from_index_results()

    if not models:
        print("No models found!")
        sys.exit(1)

    print(f"Found {len(models)} models: {models}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    tracker_script = os.path.join(script_dir, "track_llm_support.py")
    data_dir = os.path.join(os.path.dirname(script_dir), "data")

    os.makedirs(data_dir, exist_ok=True)

    results = []
    for model in models:
        print(f"\n{'='*60}")
        print(f"Processing: {model}")
        print("=" * 60)

        # Get release date (use default if not known)
        release_date = MODEL_RELEASE_DATES.get(model, "2025-01-01")

        output_file = os.path.join(data_dir, f"{model}.json")

        try:
            subprocess.run(
                [
                    sys.executable,
                    tracker_script,
                    "--model-id",
                    model,
                    "--release-date",
                    release_date,
                    "--output",
                    output_file,
                ],
                check=True,
            )

            # Load the result
            with open(output_file) as f:
                result = json.load(f)
                results.append(result)

        except subprocess.CalledProcessError as e:
            print(f"Error processing {model}: {e}")
        except Exception as e:
            print(f"Error processing {model}: {e}")

    # Write combined results
    combined_output = os.path.join(data_dir, "all_models.json")
    with open(combined_output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"All results written to {combined_output}")
    print(f"Individual results in {data_dir}/")


if __name__ == "__main__":
    main()
