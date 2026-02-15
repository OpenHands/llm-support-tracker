#!/usr/bin/env python3
"""
Script to track LLM support timestamps across OpenHands repositories.

This script takes a language model ID and release date as inputs and outputs
a JSON file containing timestamps for when the model was supported in:
- OpenHands/software-agent-sdk
- OpenHands/OpenHands frontend dropdown
- OpenHands/openhands-index-results
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional

import requests


GITHUB_API_BASE = "https://api.github.com"
REPOS = {
    "sdk": "OpenHands/software-agent-sdk",
    "frontend": "OpenHands/OpenHands",
    "index_results": "OpenHands/openhands-index-results",
}

# Files to search for model support in each repo
SEARCH_PATHS = {
    "sdk": ["openhands-sdk/openhands/sdk/llm/"],
    "frontend": ["frontend/src/utils/verified-models.ts"],
    "index_results": ["results/"],
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


def search_commits_for_model(
    repo: str, model_id: str, paths: list[str]
) -> Optional[str]:
    """
    Search for commits that mention the model ID in the specified repository.

    Args:
        repo: Repository in format "owner/repo"
        model_id: The language model ID to search for
        paths: List of paths to search in

    Returns:
        ISO timestamp of the first commit mentioning the model, or None if not found
    """
    headers = get_github_headers()

    # Try searching commits with the model ID in the message
    search_url = f"{GITHUB_API_BASE}/search/commits"
    query = f"repo:{repo} {model_id}"
    params = {"q": query, "sort": "author-date", "order": "asc", "per_page": 1}

    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("total_count", 0) > 0:
                items = data.get("items", [])
                if items:
                    commit = items[0]
                    commit_date = commit.get("commit", {}).get("author", {}).get("date")
                    if commit_date:
                        return commit_date
    except requests.RequestException as e:
        print(f"Warning: Error searching commits in {repo}: {e}", file=sys.stderr)

    return None


def search_index_results_folder(model_id: str) -> Optional[str]:
    """
    Search for when a model folder was added to openhands-index-results.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of when the folder was created, or None if not found
    """
    headers = get_github_headers()
    repo = REPOS["index_results"]

    # First, check if the folder exists
    contents_url = f"{GITHUB_API_BASE}/repos/{repo}/contents/results"

    try:
        response = requests.get(contents_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None

        contents = response.json()
        folder_name = None

        # Find the folder that matches the model ID (case-insensitive)
        for item in contents:
            if item.get("type") == "dir":
                name = item.get("name", "")
                if model_id.lower() == name.lower():
                    folder_name = name
                    break

        if not folder_name:
            return None

        # Get the first commit that added this folder
        commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
        params = {"path": f"results/{folder_name}", "per_page": 100}

        response = requests.get(commits_url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            return None

        commits = response.json()
        if commits:
            # Get the oldest commit (last in the list)
            oldest_commit = commits[-1]
            return oldest_commit.get("commit", {}).get("author", {}).get("date")

    except requests.RequestException as e:
        print(f"Warning: Error searching index results: {e}", file=sys.stderr)

    return None


def track_llm_support(model_id: str, release_date: str) -> dict:
    """
    Track when a language model was supported across OpenHands repositories.

    Args:
        model_id: The language model ID
        release_date: The release date of the model (ISO format)

    Returns:
        Dictionary containing support timestamps
    """
    result = {
        "model_id": model_id,
        "release_date": release_date,
        "sdk_support_timestamp": None,
        "frontend_support_timestamp": None,
        "index_results_timestamp": None,
    }

    # Search for SDK support
    print(f"Searching for {model_id} in software-agent-sdk...")
    sdk_timestamp = search_commits_for_model(
        REPOS["sdk"], model_id, SEARCH_PATHS["sdk"]
    )
    result["sdk_support_timestamp"] = sdk_timestamp

    # Search for frontend support
    print(f"Searching for {model_id} in OpenHands frontend...")
    frontend_timestamp = search_commits_for_model(
        REPOS["frontend"], model_id, SEARCH_PATHS["frontend"]
    )
    result["frontend_support_timestamp"] = frontend_timestamp

    # Search for index results
    print(f"Searching for {model_id} in openhands-index-results...")
    index_timestamp = search_index_results_folder(model_id)
    result["index_results_timestamp"] = index_timestamp

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Track LLM support timestamps across OpenHands repositories"
    )
    parser.add_argument(
        "--model-id",
        "-m",
        required=True,
        help="Language model ID to track",
    )
    parser.add_argument(
        "--release-date",
        "-r",
        required=True,
        help="Release date of the model (ISO format, e.g., 2024-01-15)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output JSON file path",
    )

    args = parser.parse_args()

    # Validate release date format
    try:
        datetime.fromisoformat(args.release_date.replace("Z", "+00:00"))
    except ValueError:
        print(f"Error: Invalid release date format: {args.release_date}")
        print("Please use ISO format (e.g., 2024-01-15 or 2024-01-15T00:00:00Z)")
        sys.exit(1)

    # Track LLM support
    result = track_llm_support(args.model_id, args.release_date)

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Write output
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nResults written to {args.output}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
