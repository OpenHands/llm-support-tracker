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


def get_model_search_terms(model_id: str) -> list[str]:
    """
    Get a list of search terms for a model, including the full name and family names.

    For example, "Gemini-3-Pro" would return ["Gemini-3-Pro", "Gemini-3", "Gemini 3", "gemini-3-pro"]
    """
    import re

    terms = [model_id]

    # Add lowercase version
    if model_id.lower() not in terms:
        terms.append(model_id.lower())

    # Try removing common suffixes like -Pro, -Flash, -Nano, etc.
    suffixes = ["-Pro", "-Flash", "-Nano", "-Thinking", "-Codex", "-Reasoner", ".5", "-480B", "-235B"]
    for suffix in suffixes:
        if model_id.endswith(suffix):
            base = model_id[:-len(suffix)]
            if base not in terms:
                terms.append(base)
            if base.lower() not in terms:
                terms.append(base.lower())

    # Also try with spaces instead of hyphens
    spaced = model_id.replace("-", " ")
    if spaced not in terms:
        terms.append(spaced)

    # For versioned models like "claude-sonnet-4-5", also try "claude-sonnet-4"
    version_match = re.match(r"(.+)-(\d+)-(\d+)$", model_id)
    if version_match:
        base_with_major = f"{version_match.group(1)}-{version_match.group(2)}"
        if base_with_major not in terms:
            terms.append(base_with_major)

    # For models like "Qwen3-Coder-480B", also try "qwen-3-coder" (lowercase with hyphen)
    # Convert "Qwen3" to "qwen-3", "GPT5" to "gpt-5", etc.
    normalized = re.sub(r'([a-zA-Z])(\d)', r'\1-\2', model_id).lower()
    if normalized not in terms:
        terms.append(normalized)

    # Try removing version numbers entirely for models like "DeepSeek-V3.2-Reasoner" -> "deepseek-reasoner"
    # Remove patterns like V3.2, -3-, etc.
    no_version = re.sub(r'-?[Vv]?\d+\.?\d*-?', '-', model_id).strip('-')
    no_version = re.sub(r'--+', '-', no_version)  # Clean up double hyphens
    if no_version not in terms:
        terms.append(no_version)
    if no_version.lower() not in terms:
        terms.append(no_version.lower())

    # For "Nemotron-3-Nano" type models, try "nemotron-nano" (remove middle version number)
    parts = model_id.split('-')
    if len(parts) >= 3:
        # Try removing middle numeric parts
        non_numeric_parts = [p for p in parts if not p.isdigit()]
        if len(non_numeric_parts) >= 2:
            joined = '-'.join(non_numeric_parts)
            if joined not in terms:
                terms.append(joined)
            if joined.lower() not in terms:
                terms.append(joined.lower())

    # Also try just the model family name (e.g., "Qwen" from "Qwen3-Coder-480B")
    family_match = re.match(r'^([A-Za-z]+)', model_id)
    if family_match:
        family = family_match.group(1)
        if family not in terms and len(family) > 2:
            terms.append(family)
        if family.lower() not in terms and len(family) > 2:
            terms.append(family.lower())

    return terms


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
    search_url = f"{GITHUB_API_BASE}/search/commits"
    
    # Get all search terms for this model
    search_terms = get_model_search_terms(model_id)
    
    earliest_date = None
    
    for term in search_terms:
        query = f"repo:{repo} {term}"
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
                            # Keep the earliest date found
                            if earliest_date is None or commit_date < earliest_date:
                                earliest_date = commit_date
        except requests.RequestException as e:
            print(f"Warning: Error searching commits in {repo}: {e}", file=sys.stderr)

    return earliest_date


def search_litellm_support(model_id: str) -> Optional[str]:
    """
    Search for when a model was added to BerriAI/litellm's model_prices_and_context_window.json.

    This uses binary search through commit history via the GitHub API to find 
    the first commit where the model appears in the model prices file.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of when the model was added, or None if not found
    """
    headers = get_github_headers()
    repo = "BerriAI/litellm"
    file_path = "model_prices_and_context_window.json"
    search_terms = get_model_search_terms(model_id)
    
    # First, check if model exists in current version using any search term
    current_url = f"https://raw.githubusercontent.com/{repo}/main/{file_path}"
    try:
        response = requests.get(current_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
            
        current_content = response.text.lower()
        found = False
        for term in search_terms:
            if term.lower() in current_content:
                found = True
                break
        if not found:
            return None
    except requests.RequestException:
        return None
    
    # Get commits that modified the model prices file
    commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
    all_commits = []
    page = 1
    max_pages = 10
    
    while page <= max_pages:
        params = {"path": file_path, "per_page": 100, "page": page}
        try:
            response = requests.get(commits_url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                break
            commits = response.json()
            if not commits:
                break
            all_commits.extend(commits)
            if len(commits) < 100:
                break
            page += 1
        except requests.RequestException:
            break
    
    if not all_commits:
        return None
    
    def content_has_model(content: str) -> bool:
        """Check if any search term appears in the content."""
        content_lower = content.lower()
        for term in search_terms:
            if term.lower() in content_lower:
                return True
        return False
    
    # Binary search to find the first commit where the model exists
    left, right = 0, len(all_commits) - 1
    first_commit_with_model = all_commits[0]
    
    while left <= right:
        mid = (left + right) // 2
        commit_sha = all_commits[mid].get("sha")
        
        file_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{file_path}"
        try:
            response = requests.get(file_url, headers=headers, timeout=30)
            if response.status_code == 200:
                if content_has_model(response.text):
                    first_commit_with_model = all_commits[mid]
                    left = mid + 1
                else:
                    right = mid - 1
            else:
                right = mid - 1
        except requests.RequestException:
            right = mid - 1
    
    return first_commit_with_model.get("commit", {}).get("author", {}).get("date")


def search_index_results_folder(model_id: str) -> Optional[str]:
    """
    Search for when a model first had complete benchmark results in openhands-index-results.

    A model is considered "complete" when it has results for all 5 required benchmarks:
    swe-bench, commit0, gaia, swt-bench, and swe-bench-multimodal.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of the first commit with complete results, or None if not found/incomplete
    """
    headers = get_github_headers()
    repo = REPOS["index_results"]
    required_benchmarks = {"swe-bench", "commit0", "gaia", "swt-bench", "swe-bench-multimodal"}

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

        # Get the commit history for scores.json
        commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
        params = {"path": f"results/{folder_name}/scores.json", "per_page": 100}

        response = requests.get(commits_url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            return None

        commits = response.json()
        if not commits:
            return None

        # Go through commits from oldest to newest to find first complete scores.json
        # Commits are returned newest-first, so reverse the list
        for commit in reversed(commits):
            commit_sha = commit.get("sha")
            commit_date = commit.get("commit", {}).get("author", {}).get("date")

            if not commit_sha or not commit_date:
                continue

            # Fetch scores.json at this commit
            scores_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/results/{folder_name}/scores.json"
            try:
                scores_response = requests.get(scores_url, headers=headers, timeout=30)
                if scores_response.status_code == 200:
                    scores = scores_response.json()
                    present_benchmarks = {entry.get("benchmark") for entry in scores if entry.get("benchmark")}

                    # Check if all required benchmarks are present
                    if required_benchmarks.issubset(present_benchmarks):
                        return commit_date
            except (requests.RequestException, json.JSONDecodeError):
                continue

        # No commit found with complete benchmarks
        return None

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


def extract_litellm_version_from_yaml(yaml_content: str) -> Optional[str]:
    """
    Extract the full litellm version tag from a litellm.yaml file content.

    The version is in the image.tag field, e.g., "v1.81.9-stable.gemini.3.1-pro.sonnet-4.6"

    Args:
        yaml_content: The YAML file content

    Returns:
        The full litellm version tag string, or None if not found
    """
    import re

    # Look for image tag pattern - extract the FULL tag, not just the version number
    # Can be in format: tag: v1.81.9-stable or tag: "v1.81.9-stable.gemini.3.1-pro"
    match = re.search(r'tag:\s*["\']?(v[\d.]+[^\s"\']*)', yaml_content)
    if match:
        return match.group(1)

    return None


def check_litellm_version_supports_model(version: str, model_id: str) -> bool:
    """
    Check if a specific litellm version supports a model.

    Args:
        version: Full litellm version tag (e.g., "v1.81.9-stable.gemini.3.1-pro.sonnet-4.6")
        model_id: The model ID to check

    Returns:
        True if the version supports the model, False otherwise
    """
    headers = get_github_headers()
    search_terms = get_model_search_terms(model_id)

    # Fetch model_prices_and_context_window.json at this version tag
    file_url = f"https://raw.githubusercontent.com/BerriAI/litellm/{version}/model_prices_and_context_window.json"

    try:
        response = requests.get(file_url, headers=headers, timeout=30)
        if response.status_code == 200:
            content = response.text.lower()
            # Check if any search term appears in the file
            for term in search_terms:
                if term.lower() in content:
                    return True
    except requests.RequestException:
        pass

    return False


def search_infra_proxy(model_id: str, proxy_type: str) -> Optional[str]:
    """
    Search for when a model was first supported in the infra proxy deployment.

    This works by:
    1. Getting the commit history of the litellm.yaml file
    2. For each commit (oldest to newest), extracting the deployed litellm version tag
    3. Checking if that litellm version supports the model
    4. Returning the date of the first deployment where the model is supported

    Args:
        model_id: The language model ID to search for
        proxy_type: Either "eval_proxy" or "prod_proxy"

    Returns:
        ISO timestamp of when the model was first supported, or None if not found
    """
    headers = get_github_headers()
    repo = REPOS["infra"]
    path = SEARCH_PATHS[proxy_type][0]

    # Get commit history for the litellm.yaml file
    commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
    all_commits = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        params = {"path": path, "per_page": 100, "page": page}
        try:
            response = requests.get(commits_url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                break
            commits = response.json()
            if not commits:
                break
            all_commits.extend(commits)
            if len(commits) < 100:
                break
            page += 1
        except requests.RequestException:
            break

    if not all_commits:
        return None

    # Track which versions we've already checked to avoid redundant API calls
    checked_versions: dict[str, bool] = {}

    # Go through commits from oldest to newest
    for commit in reversed(all_commits):
        commit_sha = commit.get("sha")
        commit_date = commit.get("commit", {}).get("author", {}).get("date")

        if not commit_sha or not commit_date:
            continue

        # Fetch litellm.yaml at this commit
        file_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{path}"
        try:
            file_response = requests.get(file_url, headers=headers, timeout=30)
            if file_response.status_code != 200:
                continue

            yaml_content = file_response.text
            version = extract_litellm_version_from_yaml(yaml_content)

            if not version:
                continue

            # Check if we've already verified this version
            if version in checked_versions:
                if checked_versions[version]:
                    return commit_date
                continue

            # Check if this litellm version supports the model
            supports_model = check_litellm_version_supports_model(version, model_id)
            checked_versions[version] = supports_model

            if supports_model:
                return commit_date

        except requests.RequestException:
            continue

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


def search_model_in_file_history(
    repo: str, file_path: str, model_id: str
) -> Optional[str]:
    """
    Search for when a model first appeared in a file by checking commit history.

    Goes through the commit history of the file from oldest to newest and finds
    the first commit where the model ID appears in the file content.

    Args:
        repo: Repository in format "owner/repo"
        file_path: Path to the file to check
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of the first commit where model appears, or None if not found
    """
    headers = get_github_headers()
    
    # Search for the exact model name (lowercase since we lowercase file content)
    search_term = model_id.lower()

    # Get commit history for the file
    commits_url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
    all_commits = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        params = {"path": file_path, "per_page": 100, "page": page}
        try:
            response = requests.get(commits_url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                break
            commits = response.json()
            if not commits:
                break
            all_commits.extend(commits)
            if len(commits) < 100:
                break
            page += 1
        except requests.RequestException:
            break

    if not all_commits:
        return None

    # Go through commits from oldest to newest to find first appearance
    for commit in reversed(all_commits):
        commit_sha = commit.get("sha")
        commit_date = commit.get("commit", {}).get("author", {}).get("date")

        if not commit_sha or not commit_date:
            continue

        # Fetch file content at this commit
        file_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{file_path}"
        try:
            file_response = requests.get(file_url, headers=headers, timeout=30)
            if file_response.status_code == 200:
                content = file_response.text.lower()

                # Check if the exact model name appears in the file
                if search_term in content:
                    return commit_date
        except requests.RequestException:
            continue

    return None


def get_later_timestamp(timestamp1: Optional[str], timestamp2: Optional[str]) -> Optional[str]:
    """
    Return the later of two timestamps, or whichever is not None.

    Args:
        timestamp1: First ISO timestamp (or None)
        timestamp2: Second ISO timestamp (or None)

    Returns:
        The later timestamp, or None if both are None
    """
    if timestamp1 is None:
        return timestamp2
    if timestamp2 is None:
        return timestamp1

    # Compare timestamps (ISO format strings are lexicographically comparable)
    # Normalize to comparable format
    def normalize(ts: str) -> str:
        # Extract just the date and time parts for comparison
        return ts.replace("+00:00", "Z").split(".")[0]

    return timestamp1 if normalize(timestamp1) > normalize(timestamp2) else timestamp2


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

    # Search for upstream litellm support FIRST
    # SDK support cannot be earlier than litellm support
    print(f"Searching for {model_id} in BerriAI/litellm...")
    litellm_timestamp = search_litellm_support(model_id)
    result["litellm_support_timestamp"] = adjust_timestamp_to_release(litellm_timestamp, release_date)

    # Search for SDK-specific support (special handling added for this model)
    # SDK support defaults to litellm support, but if there's SDK-specific work
    # that happened later, use that later date
    print(f"Searching for {model_id} in software-agent-sdk...")
    sdk_specific_timestamp = search_commits_for_model(
        REPOS["sdk"], model_id, SEARCH_PATHS["sdk"]
    )
    sdk_specific_timestamp = adjust_timestamp_to_release(sdk_specific_timestamp, release_date)

    # SDK support is the later of: litellm support or SDK-specific work
    # If no SDK-specific work found, default to litellm support
    if sdk_specific_timestamp is not None:
        result["sdk_support_timestamp"] = get_later_timestamp(
            result["litellm_support_timestamp"], sdk_specific_timestamp
        )
    else:
        result["sdk_support_timestamp"] = result["litellm_support_timestamp"]

    # Search for frontend support by checking file history
    print(f"Searching for {model_id} in OpenHands frontend...")
    frontend_timestamp = search_model_in_file_history(
        REPOS["frontend"], SEARCH_PATHS["frontend"][0], model_id
    )
    result["frontend_support_timestamp"] = adjust_timestamp_to_release(frontend_timestamp, release_date)

    # Search for index results
    print(f"Searching for {model_id} in openhands-index-results...")
    index_timestamp = search_index_results_folder(model_id)
    result["index_results_timestamp"] = adjust_timestamp_to_release(index_timestamp, release_date)

    # Search for eval proxy support by checking deployed litellm versions
    print(f"Searching for {model_id} in All-Hands-AI/infra eval proxy...")
    eval_proxy_timestamp = search_infra_proxy(model_id, "eval_proxy")
    eval_proxy_timestamp = adjust_timestamp_to_release(eval_proxy_timestamp, release_date)
    # Default to litellm support if no specific proxy deployment found
    result["eval_proxy_timestamp"] = eval_proxy_timestamp or result["litellm_support_timestamp"]

    # Search for prod proxy support by checking deployed litellm versions
    print(f"Searching for {model_id} in All-Hands-AI/infra prod proxy...")
    prod_proxy_timestamp = search_infra_proxy(model_id, "prod_proxy")
    prod_proxy_timestamp = adjust_timestamp_to_release(prod_proxy_timestamp, release_date)
    # Default to litellm support if no specific proxy deployment found
    result["prod_proxy_timestamp"] = prod_proxy_timestamp or result["litellm_support_timestamp"]

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
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
