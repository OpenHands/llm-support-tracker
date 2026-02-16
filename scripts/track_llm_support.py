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
    "infra": "All-Hands-AI/infra",
}

# Files to search for model support in each repo
SEARCH_PATHS = {
    "sdk": ["openhands-sdk/openhands/sdk/llm/"],
    "frontend": ["frontend/src/utils/verified-models.ts"],
    "index_results": ["results/"],
    "eval_proxy": ["k8s/evaluation/litellm.yaml"],
    "prod_proxy": ["k8s/production/litellm.yaml"],
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


def search_litellm_support(model_id: str) -> Optional[str]:
    """
    Search for when a model was added to BerriAI/litellm.

    This searches the upstream litellm repository for when the model
    was first added to model_prices_and_context_window.json.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of when the model was added, or None if not found
    """
    headers = get_github_headers()

    # Search for commits adding the model to litellm
    search_url = f"{GITHUB_API_BASE}/search/commits"
    query = f"repo:BerriAI/litellm {model_id}"
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
        print(f"Warning: Error searching litellm commits: {e}", file=sys.stderr)

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


def get_providers_from_model(model_id: str) -> list[str]:
    """
    Determine possible providers from a model ID for wildcard routing lookup.
    Returns a list of providers to check (in order of preference).
    """
    model_lower = model_id.lower()
    providers = []
    
    # Map model prefixes to provider wildcards
    # These are the wildcards configured in the infra litellm.yaml
    provider_mappings = {
        "claude": "anthropic",
        "gpt": "openai",
        "gemini": "gemini",
        "deepseek": "deepseek",
        "mistral": "mistral",
        "qwen": "together_ai",  # Qwen models often via together_ai
        "llama": "together_ai",
        "kimi": "moonshot",
    }
    
    for prefix, provider in provider_mappings.items():
        if model_lower.startswith(prefix):
            providers.append(provider)
            break
    
    # Many models can also be accessed via hosted_vllm or openrouter wildcards
    # These are fallback options that support a wide range of models
    providers.extend(["hosted_vllm", "openrouter"])
    
    return providers


def get_provider_from_model(model_id: str) -> Optional[str]:
    """
    Determine the primary provider from a model ID for wildcard routing lookup.
    """
    providers = get_providers_from_model(model_id)
    return providers[0] if providers else None


def check_wildcard_in_file(repo: str, path: str, provider: str) -> Optional[str]:
    """
    Check if a provider wildcard exists in the current file and find when it was added.
    
    Returns the date of the first commit that added the wildcard pattern.
    """
    headers = get_github_headers()
    
    # First check if the wildcard exists in the current file
    file_url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
    try:
        response = requests.get(file_url, headers=headers, timeout=30)
        if response.status_code == 200:
            import base64
            content = base64.b64decode(response.json().get("content", "")).decode("utf-8")
            wildcard_pattern = f'{provider}/*'
            
            if wildcard_pattern not in content:
                return None
            
            # Wildcard exists, find when it was first added
            # Search commit messages for when this provider was added
            commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
            params = {"path": path, "per_page": 100}
            
            response = requests.get(commits_url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                commits = response.json()
                
                # Look for commits that mention this provider
                provider_commits = []
                for commit in commits:
                    message = commit.get("commit", {}).get("message", "").lower()
                    commit_date = commit.get("commit", {}).get("author", {}).get("date")
                    if commit_date and provider.lower() in message:
                        provider_commits.append(commit_date)
                
                # If found commits mentioning the provider, return the oldest
                if provider_commits:
                    return provider_commits[-1]
                
                # Otherwise, assume it was in the initial file creation
                if commits:
                    return commits[-1].get("commit", {}).get("author", {}).get("date")
    except requests.RequestException:
        pass
    
    return None


def search_infra_proxy(model_id: str, proxy_type: str) -> Optional[str]:
    """
    Search for when a model was added to the infra proxy configuration.

    This searches:
    1. Commit messages for explicit model name mentions
    2. Provider wildcard routing (e.g., anthropic/* for claude models)

    Args:
        model_id: The language model ID to search for
        proxy_type: Either "eval_proxy" or "prod_proxy"

    Returns:
        ISO timestamp of when the model was added, or None if not found
    """
    headers = get_github_headers()
    repo = REPOS["infra"]
    path = SEARCH_PATHS[proxy_type][0]

    # Get commits that modified the litellm.yaml file
    commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
    params = {"path": path, "per_page": 100}

    try:
        response = requests.get(commits_url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            commits = response.json()
            
            # Search through commits for model name (case-insensitive)
            model_lower = model_id.lower()
            matching_commits = []
            
            for commit in commits:
                message = commit.get("commit", {}).get("message", "").lower()
                commit_date = commit.get("commit", {}).get("author", {}).get("date")
                
                if not commit_date:
                    continue
                    
                # Check if model name appears in commit message
                if model_lower in message:
                    matching_commits.append(commit_date)
            
            # If found explicit model mention, return it
            if matching_commits:
                return matching_commits[-1]  # Last in list is oldest
                
    except requests.RequestException as e:
        print(f"Warning: Error searching {proxy_type} commits: {e}", file=sys.stderr)

    # If no explicit mention, check for provider wildcard support
    # Try all possible providers (primary provider first, then fallbacks like hosted_vllm, openrouter)
    providers = get_providers_from_model(model_id)
    for provider in providers:
        wildcard_date = check_wildcard_in_file(repo, path, provider)
        if wildcard_date:
            return wildcard_date

    return None


def adjust_timestamp_to_release(timestamp: Optional[str], release_date: str) -> Optional[str]:
    """
    Adjust a support timestamp to not be earlier than the model's release date.
    
    If the support infrastructure (e.g., wildcard routing) existed before the model
    was released, the effective support date is the release date itself.
    
    Args:
        timestamp: The detected support timestamp (ISO format)
        release_date: The model's release date (ISO format)
    
    Returns:
        The later of the two dates, or None if timestamp is None
    """
    if timestamp is None:
        return None
    
    from datetime import datetime
    
    # Parse dates (handle various ISO formats)
    def parse_date(date_str: str) -> datetime:
        # Try different formats
        for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.replace("+00:00", "Z").split(".")[0] + "Z", "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
        # Fallback: just parse the date part
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    
    try:
        support_dt = parse_date(timestamp)
        release_dt = parse_date(release_date)
        
        # If support was available before release, use release date
        if support_dt < release_dt:
            # Return release date at midnight UTC
            return release_date + "T00:00:00Z" if "T" not in release_date else release_date
        
        return timestamp
    except (ValueError, TypeError):
        return timestamp


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
        "eval_proxy_timestamp": None,
        "prod_proxy_timestamp": None,
        "litellm_support_timestamp": None,
    }

    # Search for SDK support
    print(f"Searching for {model_id} in software-agent-sdk...")
    sdk_timestamp = search_commits_for_model(
        REPOS["sdk"], model_id, SEARCH_PATHS["sdk"]
    )
    result["sdk_support_timestamp"] = adjust_timestamp_to_release(sdk_timestamp, release_date)

    # Search for frontend support
    print(f"Searching for {model_id} in OpenHands frontend...")
    frontend_timestamp = search_commits_for_model(
        REPOS["frontend"], model_id, SEARCH_PATHS["frontend"]
    )
    result["frontend_support_timestamp"] = adjust_timestamp_to_release(frontend_timestamp, release_date)

    # Search for index results
    print(f"Searching for {model_id} in openhands-index-results...")
    index_timestamp = search_index_results_folder(model_id)
    result["index_results_timestamp"] = adjust_timestamp_to_release(index_timestamp, release_date)

    # Search for eval proxy support
    print(f"Searching for {model_id} in All-Hands-AI/infra eval proxy...")
    eval_proxy_timestamp = search_infra_proxy(model_id, "eval_proxy")
    result["eval_proxy_timestamp"] = adjust_timestamp_to_release(eval_proxy_timestamp, release_date)

    # Search for prod proxy support
    print(f"Searching for {model_id} in All-Hands-AI/infra prod proxy...")
    prod_proxy_timestamp = search_infra_proxy(model_id, "prod_proxy")
    result["prod_proxy_timestamp"] = adjust_timestamp_to_release(prod_proxy_timestamp, release_date)

    # Search for upstream litellm support
    print(f"Searching for {model_id} in BerriAI/litellm...")
    litellm_timestamp = search_litellm_support(model_id)
    result["litellm_support_timestamp"] = adjust_timestamp_to_release(litellm_timestamp, release_date)

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
