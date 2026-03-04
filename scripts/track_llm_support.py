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
import re
import sys
from datetime import datetime
from typing import Optional

import requests


GITHUB_API_BASE = "https://api.github.com"

# Tier 1 model patterns (priority models)
TIER_1_PATTERNS = [
    r"^claude-sonnet-",      # Claude Sonnet
    r"^claude-opus-",        # Claude Opus
    r"^Gemini-.*-Pro$",      # Gemini Pro
    r"^Gemini-.*-Flash$",    # Gemini Flash
    r"^GPT-5",               # GPT-5*
    r"^GLM-",                # GLM
    r"^MiniMax-",            # MiniMax
    r"^Qwen3-Coder-",        # Qwen3-Coder-*
    r"^Kimi-K2",             # Kimi-K2*
]


def get_model_tier(model_id: str) -> int:
    """
    Determine the tier of a model based on its ID.
    
    Tier 1: Priority models (Claude Sonnet/Opus, Gemini Pro/Flash, GPT-5*, 
            GLM, MiniMax, Qwen3-Coder-480B, Kimi-K2)
    Tier 2: All other models
    
    Args:
        model_id: The model ID to check
        
    Returns:
        1 for tier 1 models, 2 for tier 2
    """
    for pattern in TIER_1_PATTERNS:
        if re.match(pattern, model_id):
            return 1
    return 2


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
    
    For example, "Gemini-3-Pro" would return ["Gemini-3-Pro", "gemini-3-pro", "Gemini-3", ...]
    """
    import re
    
    # Model-specific aliases for frontend/SDK search (different naming conventions)
    SEARCH_ALIASES = {
        "kimi-k2-thinking": ["kimi-k2-0711-preview", "kimi-k2"],
        "kimi-k2.5": ["kimi-k2.5", "kimi-k2-5"],
        "deepseek-v3.2-reasoner": ["deepseek-reasoner", "deepseek-v3.2"],
        "glm-4.7": ["glm-4", "glm4"],
        "glm-5": ["glm-5", "glm5"],
        "qwen3-coder-next": ["qwen3-coder-next", "qwen-3-coder-next"],
    }
    
    terms = [model_id]
    
    # Always include lowercase version for case-insensitive matching
    lowercase = model_id.lower()
    if lowercase not in terms:
        terms.append(lowercase)
    
    # Add model-specific aliases
    if lowercase in SEARCH_ALIASES:
        for alias in SEARCH_ALIASES[lowercase]:
            if alias not in terms:
                terms.append(alias)
    
    # Try removing common suffixes like -Pro, -Flash, -Nano, etc.
    suffixes = ["-Pro", "-Flash", "-Nano", "-Thinking", "-Codex", "-Reasoner", ".5", "-480B", "-235B"]
    for suffix in suffixes:
        if model_id.endswith(suffix):
            base = model_id[:-len(suffix)]
            if base not in terms:
                terms.append(base)
            # Also add lowercase version
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
    
    # Also try just the model family name (e.g., "Qwen" from "Qwen3-Coder-480B")
    family_match = re.match(r'^([A-Za-z]+)', model_id)
    if family_match:
        family = family_match.group(1)
        if family not in terms and len(family) > 2:
            terms.append(family)
    
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
    # Commit search requires a special Accept header
    headers["Accept"] = "application/vnd.github.cloak-preview+json"
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


def get_litellm_model_search_terms(model_id: str) -> list[str]:
    """
    Get search terms for finding a model in litellm's model_prices_and_context_window.json.
    
    Returns terms that should match as JSON keys in the model prices file.
    """
    # Model-specific aliases only when litellm uses a different name
    MODEL_ALIASES = {
        # DeepSeek V3.2 Reasoner - use versioned name only
        # Note: "deepseek-reasoner" is a separate unversioned model that predates V3.2
        "deepseek-v3.2-reasoner": ["deepseek/deepseek-v3.2"],
        # Gemini 3 Pro/Flash - litellm uses "preview" suffix
        "gemini-3-pro": ["gemini-3-pro-preview"],
        "gemini-3-flash": ["gemini-3-flash-preview"],
        # GLM-5 - litellm uses zai/ prefix
        "glm-5": ["zai/glm-5"],
        # Nemotron 3 Nano - check for nvidia nemotron nano variants
        "nemotron-3-nano": ["nvidia-nemotron-nano"],
        # Qwen3 Coder models - litellm uses qwen. prefix on bedrock
        "qwen3-coder-480b": ["qwen3-coder-480b"],
        "qwen3-coder-next": ["qwen.qwen3-coder-next"],
    }
    
    model_lower = model_id.lower()
    
    # Use alias if defined, otherwise use the model ID as-is
    if model_lower in MODEL_ALIASES:
        return MODEL_ALIASES[model_lower]
    
    return [model_lower]


def check_model_in_litellm_json(content: str, model_id: str) -> bool:
    """
    Check if a model exists as a key in the litellm model_prices_and_context_window.json content.
    
    This checks for the model name as a JSON key to avoid false positives from
    partial string matches in comments or other fields.
    
    Args:
        content: The JSON file content (as string)
        model_id: The model ID to search for
    
    Returns:
        True if the model exists as a key in the JSON
    """
    search_terms = get_litellm_model_search_terms(model_id)
    content_lower = content.lower()
    
    for term in search_terms:
        # Check for the model as a JSON key (surrounded by quotes and followed by colon)
        # Pattern: "model_name": { or "provider/model_name": {
        if f'"{term}":' in content_lower or f'/{term}":' in content_lower:
            return True
    
    return False


# Module-level cache for SDK repo
_sdk_cache = {
    "temp_dir": None,
}


def _get_sdk_repo():
    """Get or create the cached SDK repo clone."""
    import subprocess
    import tempfile
    
    if _sdk_cache["temp_dir"] is not None:
        return _sdk_cache
    
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        repo_url = f"https://{token}@github.com/OpenHands/software-agent-sdk.git"
    else:
        repo_url = "https://github.com/OpenHands/software-agent-sdk.git"
    
    temp_dir = tempfile.mkdtemp(prefix="sdk_")
    
    # Clone the repo (sparse checkout for just the llm directory)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, temp_dir],
        capture_output=True,
        check=True,
        timeout=120,
    )
    
    _sdk_cache["temp_dir"] = temp_dir
    
    return _sdk_cache


def cleanup_sdk_cache():
    """Clean up the SDK repo cache."""
    import shutil
    if _sdk_cache["temp_dir"]:
        shutil.rmtree(_sdk_cache["temp_dir"], ignore_errors=True)
        _sdk_cache["temp_dir"] = None


def search_sdk_for_model(model_id: str) -> Optional[str]:
    """
    Search for when a model was first added to the SDK.
    
    Uses git log -G (grep) to find the first commit that introduced the model name.
    Searches only model_features.py where model lists are defined.
    
    Args:
        model_id: The language model ID to search for
        
    Returns:
        ISO timestamp of when the model was first added, or None
    """
    import subprocess
    import re
    
    try:
        cache = _get_sdk_repo()
        temp_dir = cache["temp_dir"]
        
        # Get search terms for this model
        search_terms = get_model_search_terms(model_id)
        
        earliest_date = None
        
        # Only search model_features.py where model lists are defined
        search_path = "openhands-sdk/openhands/sdk/llm/utils/model_features.py"
        
        for term in search_terms:
            # Escape regex special chars but keep it as a literal search
            escaped_term = re.escape(term)
            
            # Use git log -G (grep in diff) to find when term was added
            result = subprocess.run(
                ["git", "log", "-G", escaped_term, "--format=%aI", "--reverse", "--", search_path],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                dates = result.stdout.strip().split("\n")
                if dates:
                    commit_date = dates[0]  # First commit (oldest)
                    if earliest_date is None or commit_date < earliest_date:
                        earliest_date = commit_date
        
        return earliest_date
        
    except Exception as e:
        print(f"Warning: Error searching SDK: {e}", file=sys.stderr)
        return None


# Module-level cache for frontend repo
_frontend_cache = {
    "temp_dir": None,
}


def _get_frontend_repo():
    """Get or create the cached frontend repo clone."""
    import subprocess
    import tempfile
    
    if _frontend_cache["temp_dir"] is not None:
        return _frontend_cache
    
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        repo_url = f"https://{token}@github.com/OpenHands/OpenHands.git"
    else:
        repo_url = "https://github.com/OpenHands/OpenHands.git"
    
    temp_dir = tempfile.mkdtemp(prefix="frontend_")
    
    # Clone the repo with filter for performance
    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, temp_dir],
        capture_output=True,
        check=True,
        timeout=180,
    )
    
    _frontend_cache["temp_dir"] = temp_dir
    
    return _frontend_cache


def cleanup_frontend_cache():
    """Clean up the frontend repo cache."""
    import shutil
    if _frontend_cache["temp_dir"]:
        shutil.rmtree(_frontend_cache["temp_dir"], ignore_errors=True)
        _frontend_cache["temp_dir"] = None


def search_frontend_for_model(model_id: str) -> Optional[str]:
    """
    Search for when a model was first added to the frontend.
    
    Uses git log -G to find the first commit that introduced the model name
    in verified-models.ts.
    
    Args:
        model_id: The language model ID to search for
        
    Returns:
        ISO timestamp of when the model was first added, or None
    """
    import subprocess
    import re
    
    try:
        cache = _get_frontend_repo()
        temp_dir = cache["temp_dir"]
        
        # Get search terms for this model
        search_terms = get_model_search_terms(model_id)
        
        earliest_date = None
        
        # Search in verified-models.ts
        search_path = "frontend/src/utils/verified-models.ts"
        
        for term in search_terms:
            # Escape regex special chars
            escaped_term = re.escape(term)
            
            # Use git log -G to find when term was added
            result = subprocess.run(
                ["git", "log", "-G", escaped_term, "--format=%aI", "--reverse", "--", search_path],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                dates = result.stdout.strip().split("\n")
                if dates:
                    commit_date = dates[0]  # First commit (oldest)
                    if earliest_date is None or commit_date < earliest_date:
                        earliest_date = commit_date
        
        return earliest_date
        
    except Exception as e:
        print(f"Warning: Error searching frontend: {e}", file=sys.stderr)
        return None


# Module-level cache for litellm repo
_litellm_cache = {
    "temp_dir": None,
    "tags": None,
    "tag_dates": None,
    "current_content": None,
}


def _get_litellm_repo():
    """Get or create the cached litellm repo clone."""
    import subprocess
    import tempfile
    import re
    
    if _litellm_cache["temp_dir"] is not None:
        return _litellm_cache
    
    repo_url = "https://github.com/BerriAI/litellm.git"
    file_path = "model_prices_and_context_window.json"
    
    temp_dir = tempfile.mkdtemp(prefix="litellm_")
    
    # Shallow clone with tags - fast initial clone
    subprocess.run(
        ["git", "clone", "--depth=1", "--no-single-branch", repo_url, temp_dir],
        capture_output=True,
        check=True,
        timeout=120,
    )
    
    # Fetch all tags
    subprocess.run(
        ["git", "fetch", "--tags", "--depth=1"],
        cwd=temp_dir,
        capture_output=True,
        check=True,
        timeout=60,
    )
    
    # Read current content
    current_file = os.path.join(temp_dir, file_path)
    with open(current_file) as f:
        current_content = f.read()
    
    # Get all stable version tags with their dates
    result = subprocess.run(
        ["git", "tag", "-l", "v*", "--format=%(refname:short) %(creatordate:iso-strict)"],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    
    all_tags = []
    tag_dates = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        tag, date = parts
        # Match stable version tags:
        # - Pure versions: v1.2.3, v1.2.3.4
        # - Stable releases: v1.2.3-stable, v1.2.3-stable.model-name, etc.
        # Exclude: -nightly, .rc, .dev variants
        if re.match(r'^v\d+\.\d+(\.\d+)?(\.\d+)?(-stable.*)?$', tag):
            if '-nightly' not in tag and '.rc' not in tag and '.dev' not in tag:
                all_tags.append(tag)
                tag_dates[tag] = date
    
    # Sort tags by date (newest first for binary search)
    # Using date is more accurate than version number because -stable.xxx patches
    # may be released after newer base versions
    all_tags.sort(key=lambda t: tag_dates.get(t, ""), reverse=True)
    
    _litellm_cache["temp_dir"] = temp_dir
    _litellm_cache["tags"] = all_tags
    _litellm_cache["tag_dates"] = tag_dates
    _litellm_cache["current_content"] = current_content
    
    return _litellm_cache


def cleanup_litellm_cache():
    """Clean up the litellm repo cache."""
    import shutil
    if _litellm_cache["temp_dir"]:
        shutil.rmtree(_litellm_cache["temp_dir"], ignore_errors=True)
        _litellm_cache["temp_dir"] = None
        _litellm_cache["tags"] = None
        _litellm_cache["tag_dates"] = None
        _litellm_cache["current_content"] = None


def find_litellm_versions_supporting_model(model_id: str) -> list[str]:
    """
    Find all litellm versions (tags) that support the given model.

    Scans recent tags to find versions that include the model.
    Due to release branching, models may not appear monotonically across tags.
    
    Strategy: Scan the most recent 100 tags (covers ~6 months of releases),
    which should be sufficient to find the first supporting version.

    Args:
        model_id: The language model ID to search for

    Returns:
        List of version tags that support the model (newest first by date)
    """
    import subprocess
    
    file_path = "model_prices_and_context_window.json"
    
    try:
        cache = _get_litellm_repo()
        temp_dir = cache["temp_dir"]
        all_tags = cache["tags"]
        current_content = cache["current_content"]
        
        # Check if model exists in current version
        if not check_model_in_litellm_json(current_content, model_id):
            return []
        
        if not all_tags:
            return []
        
        # Scan through recent tags (sorted newest first by date)
        # Limit to 100 most recent tags for performance
        tags_to_check = all_tags[:100]
        supporting_tags = []
        
        for tag in tags_to_check:
            # Use git show to read file at tag (faster than checkout)
            result = subprocess.run(
                ["git", "show", f"{tag}:{file_path}"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0 and check_model_in_litellm_json(result.stdout, model_id):
                supporting_tags.append(tag)
        
        return supporting_tags
        
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        print(f"Warning: Error searching litellm: {e}", file=sys.stderr)
        return []


def search_litellm_support(model_id: str) -> Optional[str]:
    """
    Search for when a model was first supported in a LiteLLM stable release.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of the earliest LiteLLM version that supports the model
    """
    versions = find_litellm_versions_supporting_model(model_id)
    if not versions:
        return None
    
    cache = _get_litellm_repo()
    tag_dates = cache["tag_dates"]
    
    # versions is sorted newest first, so the last one is the earliest
    earliest_version = versions[-1]
    return tag_dates.get(earliest_version)


# Module-level cache for index results repo
_index_results_cache = {
    "temp_dir": None,
}


def _get_index_results_repo():
    """Get or create the cached index results repo clone."""
    import subprocess
    import tempfile
    
    if _index_results_cache["temp_dir"] is not None:
        return _index_results_cache
    
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        repo_url = f"https://{token}@github.com/OpenHands/openhands-index-results.git"
    else:
        repo_url = "https://github.com/OpenHands/openhands-index-results.git"
    
    temp_dir = tempfile.mkdtemp(prefix="index_results_")
    
    # Clone the repo with filter for performance
    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, temp_dir],
        capture_output=True,
        check=True,
        timeout=180,
    )
    
    _index_results_cache["temp_dir"] = temp_dir
    
    return _index_results_cache


def cleanup_index_results_cache():
    """Clean up the index results repo cache."""
    import shutil
    if _index_results_cache["temp_dir"]:
        shutil.rmtree(_index_results_cache["temp_dir"], ignore_errors=True)
        _index_results_cache["temp_dir"] = None


def search_index_results_for_model(model_id: str) -> Optional[str]:
    """
    Search for when a model folder was added to openhands-index-results.
    
    Uses local git clone to find the first commit that added results for this model.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of when the folder was created, or None if not found
    """
    import subprocess
    
    try:
        cache = _get_index_results_repo()
        temp_dir = cache["temp_dir"]
        
        # Check if the folder exists (case-insensitive search)
        results_dir = os.path.join(temp_dir, "results")
        if not os.path.exists(results_dir):
            return None
        
        folder_name = None
        for name in os.listdir(results_dir):
            if model_id.lower() == name.lower():
                folder_name = name
                break
        
        if not folder_name:
            return None
        
        # Get the first commit that added this folder using git log
        result = subprocess.run(
            ["git", "log", "--format=%aI", "--reverse", "--diff-filter=A", "--", f"results/{folder_name}"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            dates = result.stdout.strip().split("\n")
            if dates:
                return dates[0]  # First commit (oldest)
        
        return None
        
    except Exception as e:
        print(f"Warning: Error searching index results: {e}", file=sys.stderr)
        return None


# Keep old function for backwards compatibility (unused but referenced in tests)
def search_index_results_folder(model_id: str) -> Optional[str]:
    """Deprecated: Use search_index_results_for_model instead."""
    return search_index_results_for_model(model_id)


# Module-level cache for infra repo
_infra_cache = {
    "temp_dir": None,
    "eval_proxy_history": None,  # List of (date, version) tuples, oldest first
    "prod_proxy_history": None,
}


def _get_infra_repo():
    """Get or create the cached infra repo clone."""
    import subprocess
    import tempfile
    import re
    
    if _infra_cache["temp_dir"] is not None:
        return _infra_cache
    
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        repo_url = f"https://{token}@github.com/All-Hands-AI/infra.git"
    else:
        repo_url = "https://github.com/All-Hands-AI/infra.git"
    
    temp_dir = tempfile.mkdtemp(prefix="infra_")
    
    # Clone the repo
    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, temp_dir],
        capture_output=True,
        check=True,
        timeout=120,
    )
    
    _infra_cache["temp_dir"] = temp_dir
    
    # Build version history for both proxy types
    for proxy_type, path in [("eval_proxy", "k8s/evaluation/litellm.yaml"), 
                              ("prod_proxy", "k8s/production/litellm.yaml")]:
        history = []
        
        # Get all commits that modified this file, with dates
        result = subprocess.run(
            ["git", "log", "--format=%H %aI", "--follow", "--", path],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            _infra_cache[f"{proxy_type}_history"] = []
            continue
        
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))  # (sha, date)
        
        # Process commits oldest to newest
        for sha, commit_date in reversed(commits):
            # Get file content at this commit
            result = subprocess.run(
                ["git", "show", f"{sha}:{path}"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                continue
            
            # Extract the litellm image tag
            tag_match = re.search(r'tag:\s*["\']?(v[\d.]+[^"\'\s]*)', result.stdout)
            if tag_match:
                history.append((commit_date, tag_match.group(1)))
        
        _infra_cache[f"{proxy_type}_history"] = history
    
    return _infra_cache


def cleanup_infra_cache():
    """Clean up the infra repo cache."""
    import shutil
    if _infra_cache["temp_dir"]:
        shutil.rmtree(_infra_cache["temp_dir"], ignore_errors=True)
        _infra_cache["temp_dir"] = None
        _infra_cache["eval_proxy_history"] = None
        _infra_cache["prod_proxy_history"] = None


def search_infra_proxy_for_model_name(model_id: str, proxy_type: str) -> Optional[str]:
    """
    Search for when a model name first appeared in the proxy config.
    
    This does a git log search for the model name in the litellm.yaml file.
    
    Args:
        model_id: The language model ID to search for
        proxy_type: Either "eval_proxy" or "prod_proxy"
    
    Returns:
        ISO timestamp of when the model name first appeared, or None
    """
    import subprocess
    
    path_map = {
        "eval_proxy": "k8s/evaluation/litellm.yaml",
        "prod_proxy": "k8s/production/litellm.yaml",
    }
    path = path_map.get(proxy_type)
    if not path:
        return None
    
    try:
        cache = _get_infra_repo()
        temp_dir = cache["temp_dir"]
        
        if not temp_dir:
            return None
        
        # Search for the model name (case-insensitive)
        model_lower = model_id.lower()
        
        # Get all commits that modified this file
        result = subprocess.run(
            ["git", "log", "--format=%H %aI", "--follow", "--", path],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            return None
        
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))  # (sha, date)
        
        # Process commits oldest to newest, find first one containing the model
        first_appearance = None
        for sha, commit_date in reversed(commits):
            result = subprocess.run(
                ["git", "show", f"{sha}:{path}"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                continue
            
            content_lower = result.stdout.lower()
            # Check for model_name entry with this model
            if f'model_name: "{model_lower}"' in content_lower or f"model_name: '{model_lower}'" in content_lower:
                first_appearance = commit_date
                break
        
        return first_appearance
        
    except Exception as e:
        print(f"Warning: Error searching infra proxy for model name: {e}", file=sys.stderr)
        return None


def search_infra_proxy(model_id: str, proxy_type: str, valid_versions: list[str] = None) -> Optional[str]:
    """
    Search for when a model was first usable via the infra proxy.

    This searches for two things:
    1. When the model name first appeared directly in the proxy config
    2. When a litellm version supporting the model was first deployed
    
    Returns the earlier of the two dates.

    Args:
        model_id: The language model ID to search for
        proxy_type: Either "eval_proxy" or "prod_proxy"
        valid_versions: List of litellm version tags that support the model.
                       Can be None if no official litellm support yet.

    Returns:
        ISO timestamp of when the model became usable, or None
    """
    timestamps = []
    
    # Method 1: Check if model name appears directly in config
    model_name_timestamp = search_infra_proxy_for_model_name(model_id, proxy_type)
    if model_name_timestamp:
        timestamps.append(model_name_timestamp)
    
    # Method 2: Check for litellm version deployment (if we have valid versions)
    if valid_versions:
        try:
            cache = _get_infra_repo()
            history = cache.get(f"{proxy_type}_history", [])
            
            if history:
                valid_set = set(valid_versions)
                for commit_date, deployed_version in history:
                    if deployed_version in valid_set:
                        timestamps.append(commit_date)
                        break
        except Exception as e:
            print(f"Warning: Error searching infra proxy history: {e}", file=sys.stderr)
    
    if not timestamps:
        return None
    
    # Return the earliest timestamp
    if len(timestamps) == 1:
        return timestamps[0]
    
    # Parse and compare
    from datetime import datetime
    def parse_ts(ts):
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(ts.replace("Z", "+00:00") if "Z" in ts else ts, fmt)
            except ValueError:
                continue
        return None
    
    parsed = [(t, parse_ts(t)) for t in timestamps]
    parsed = [(t, p) for t, p in parsed if p is not None]
    if parsed:
        earliest = min(parsed, key=lambda x: x[1])
        return earliest[0]
    
    return timestamps[0]


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
        "tier": get_model_tier(model_id),
        "sdk_support_timestamp": None,
        "frontend_support_timestamp": None,
        "index_results_timestamp": None,
        "eval_proxy_timestamp": None,
        "prod_proxy_timestamp": None,
        "litellm_support_timestamp": None,
    }

    # Search for upstream litellm support FIRST
    # We need this before SDK since SDK falls back to litellm support
    print(f"Searching for {model_id} in BerriAI/litellm...")
    valid_versions = find_litellm_versions_supporting_model(model_id)
    
    if valid_versions:
        cache = _get_litellm_repo()
        tag_dates = cache["tag_dates"]
        earliest_version = valid_versions[-1]  # Last is earliest (sorted newest first)
        official_litellm_timestamp = tag_dates.get(earliest_version)
    else:
        official_litellm_timestamp = None

    # Search for eval proxy support
    # Find when a litellm version that supports the model was first deployed
    print(f"Searching for {model_id} in All-Hands-AI/infra eval proxy...")
    eval_proxy_timestamp = search_infra_proxy(model_id, "eval_proxy", valid_versions)
    result["eval_proxy_timestamp"] = adjust_timestamp_to_release(eval_proxy_timestamp, release_date)

    # Search for prod proxy support
    print(f"Searching for {model_id} in All-Hands-AI/infra prod proxy...")
    prod_proxy_timestamp = search_infra_proxy(model_id, "prod_proxy", valid_versions)
    result["prod_proxy_timestamp"] = adjust_timestamp_to_release(prod_proxy_timestamp, release_date)

    # Compute litellm_support_timestamp as the earliest of:
    # 1. Official LiteLLM support (from BerriAI/litellm)
    # 2. Eval proxy (model in k8s/evaluation/litellm.yaml)
    # 3. Prod proxy (model in k8s/production/litellm.yaml)
    # This is because if a model is in our proxy configs, we can use it via litellm
    litellm_candidates = [
        official_litellm_timestamp,
        eval_proxy_timestamp,
        prod_proxy_timestamp,
    ]
    litellm_candidates = [t for t in litellm_candidates if t is not None]
    if litellm_candidates:
        # Parse and find earliest
        from datetime import datetime
        def parse_ts(ts):
            # Handle various formats
            for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(ts.replace("Z", "+00:00") if "Z" in ts else ts, fmt)
                except ValueError:
                    continue
            return None
        
        parsed = [(t, parse_ts(t)) for t in litellm_candidates]
        parsed = [(t, p) for t, p in parsed if p is not None]
        if parsed:
            earliest = min(parsed, key=lambda x: x[1])
            litellm_timestamp = earliest[0]
        else:
            litellm_timestamp = None
    else:
        litellm_timestamp = None
    
    result["litellm_support_timestamp"] = adjust_timestamp_to_release(litellm_timestamp, release_date)

    # Search for SDK support using local git clone
    # If no SDK-specific features found, fall back to litellm support
    # (SDK can use any model that litellm supports)
    print(f"Searching for {model_id} in software-agent-sdk...")
    sdk_timestamp = search_sdk_for_model(model_id)
    if sdk_timestamp is None and litellm_timestamp is not None:
        # Fall back to litellm support - SDK supports all litellm models
        sdk_timestamp = litellm_timestamp
    result["sdk_support_timestamp"] = adjust_timestamp_to_release(sdk_timestamp, release_date)

    # Search for frontend support using local git clone
    print(f"Searching for {model_id} in OpenHands frontend...")
    frontend_timestamp = search_frontend_for_model(model_id)
    result["frontend_support_timestamp"] = adjust_timestamp_to_release(frontend_timestamp, release_date)

    # Search for index results using local git clone
    print(f"Searching for {model_id} in openhands-index-results...")
    index_timestamp = search_index_results_for_model(model_id)
    result["index_results_timestamp"] = adjust_timestamp_to_release(index_timestamp, release_date)

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
