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
    r"^Qwen3-Coder-",        # Qwen3-Coder-*
    r"^MiniMax-M2\.[57]$",   # MiniMax-M2.5 and M2.7 (M2.1 superseded before frontend support)
    r"^Kimi-K2\.[56]$",       # Kimi-K2.5 and K2.6 (K2-Thinking superseded before frontend support)
    r"^Nemotron-3-Super$",   # Nemotron-3-Super only
    r"^(?i:trinity-large-thinking)$",  # Arcee Trinity Large Thinking
]

# Global model aliases map.
# Maps each canonical model ID (from openhands-index-results) to all known aliases
# used across different systems (frontend, SDK, LiteLLM, proxy configs).
# These are EXACT matches - no pattern matching or substring matching.
MODEL_ALIASES: dict[str, list[str]] = {
    # Anthropic Claude models
    "claude-sonnet-4-5": [
        "claude-sonnet-4-5-20250929",  # Frontend verified-models.ts
    ],
    "claude-sonnet-4-6": [
        # NOT YET IN FRONTEND - no aliases
    ],
    "claude-opus-4-5": [
        "claude-opus-4-5-20251101",  # Frontend verified-models.ts
    ],
    "claude-opus-4-6": [
        "claude-opus-4-6",  # Frontend verified-models.ts (same name)
    ],
    "claude-opus-4-7": [
        # NOT YET IN FRONTEND - no aliases
    ],
    # Arcee AI models
    "trinity-large-thinking": [
        "Trinity-Large-Thinking",
        "arcee-ai/trinity-large-thinking",
        "openrouter/arcee-ai/trinity-large-thinking",
    ],
    # DeepSeek models
    "DeepSeek-V3.2-Reasoner": [
        "deepseek/deepseek-v3.2",  # LiteLLM naming
        "deepseek-v3.2-reasoner",  # Lowercase variant
    ],
    # GLM models (Z-AI/Zhipu)
    "GLM-4.7": [
        "glm-4.7",
        "zai/glm-4.7",           # LiteLLM direct naming
        "zai.glm-4.7",           # LiteLLM dot notation
        "glm-4-7-251222",        # LiteLLM versioned
        "openrouter/z-ai/glm-4.7",
    ],
    "GLM-5": [
        "glm-5",
        "zai/glm-5",             # LiteLLM direct naming
        "zai/glm-5-code",        # Code variant
        "openrouter/z-ai/glm-5",
    ],
    "GLM-5.1": [
        "glm-5.1",
        "zai/glm-5.1",          # LiteLLM direct naming
        "zai/glm-5.1-code",     # Code variant
        "openrouter/z-ai/glm-5.1",
    ],
    # OpenAI GPT models
    "GPT-5.2": [
        "gpt-5.2",  # Frontend verified-models.ts
    ],
    "GPT-5.2-Codex": [
        "gpt-5.2-codex",  # Frontend verified-models.ts
    ],
    "GPT-5.4": [
        "gpt-5.4",      # API model name
        "gpt-5.4-pro",  # Pro variant API model name
    ],
    "GPT-5.5": [
        "gpt-5.5",      # API model name
        "gpt-5.5-pro",  # Pro variant API model name
    ],
    # Google Gemini models
    "Gemini-3-Pro": [
        "gemini-3-pro-preview",  # Frontend verified-models.ts
        "gemini-3-pro",
    ],
    "Gemini-3-Flash": [
        "gemini-3-flash-preview",  # Frontend verified-models.ts
        "gemini-3-flash",
    ],
    "Gemini-3.1-Pro": [
        "gemini-3.1-pro-preview",  # Frontend verified-models.ts
        "gemini-3.1-pro",
        "gemini/gemini-3.1-pro",   # LiteLLM naming
    ],
    # Moonshot Kimi models
    "Kimi-K2-Thinking": [
        "kimi-k2-thinking",              # The actual model name
        "kimi-k2-thinking-turbo",        # Turbo variant
        "moonshot/kimi-k2-thinking",     # LiteLLM naming
        "moonshot.kimi-k2-thinking",     # LiteLLM dot notation
        "kimi-k2-thinking-251104",       # LiteLLM versioned
    ],
    "Kimi-K2.5": [
        "kimi-k2.5",
        "moonshot/kimi-k2.5",            # LiteLLM naming
        "moonshotai.kimi-k2.5",          # LiteLLM dot notation
        "openrouter/moonshotai/kimi-k2.5",
    ],
    "Kimi-K2.6": [
        "kimi-k2.6",                    # Lowercase variant
        "kimi-k2.6-code-preview",       # Code preview variant
        "kimi-k2.6-code",             # Code variant
        "moonshot/kimi-k2.6-code-preview",  # LiteLLM naming
    ],
    # MiniMax models
    "MiniMax-M2.1": [
        "minimax-m2.1",
        "minimax/MiniMax-M2.1",          # LiteLLM naming
        "minimax.minimax-m2.1",          # LiteLLM dot notation
        "openrouter/minimax/minimax-m2.1",
    ],
    "MiniMax-M2.5": [
        "minimax-m2.5",                  # Frontend verified-models.ts
        "minimax/MiniMax-M2.5",          # LiteLLM naming
        "openrouter/minimax/minimax-m2.5",
    ],
    "MiniMax-M2.7": [
        "minimax-m2.7",                  # Lowercase variant
        "minimax/MiniMax-M2.7",          # LiteLLM naming
        "openrouter/minimax/minimax-m2.7",
    ],
    # NVIDIA Nemotron models
    "Nemotron-3-Nano": [
        "nemotron-3-nano",
        "nvidia.nemotron-nano-3-30b",    # LiteLLM naming (30B variant)
    ],
    # Alibaba Qwen models
    "Qwen3-Coder-480B": [
        "qwen3-coder-480b",  # Frontend verified-models.ts
    ],
    "Qwen3-Coder-Next": [
        "qwen3-coder-next",
        "qwen.qwen3-coder-next",  # LiteLLM bedrock naming
    ],
    "Qwen3.6-Plus": [
        "dashscope/qwen3.6-plus",  # LiteLLM DashScope naming
    ],
}


def get_model_aliases(model_id: str) -> list[str]:
    """
    Get all known aliases for a model ID.

    Returns the model ID itself plus any aliases defined in MODEL_ALIASES.
    Git searches are case-sensitive, so we include both original case and
    lowercase versions when they differ.

    Args:
        model_id: The canonical model ID

    Returns:
        List of all known names for this model (including the model_id itself)
    """
    seen = set()  # Track exact strings to avoid duplicates
    aliases = []

    def add_alias(alias: str):
        """Add an alias if not already present (exact match)."""
        if alias not in seen:
            seen.add(alias)
            aliases.append(alias)

    # Always include the model ID itself
    add_alias(model_id)

    # Add lowercase version if different (git search is case-sensitive)
    if model_id.lower() != model_id:
        add_alias(model_id.lower())

    # Add any defined aliases (check both exact key and lowercase key)
    model_lower = model_id.lower()
    for key, value in MODEL_ALIASES.items():
        if key == model_id or key.lower() == model_lower:
            for alias in value:
                add_alias(alias)
                # Also add lowercase if different
                if alias.lower() != alias:
                    add_alias(alias.lower())

    return aliases


def get_model_tier(model_id: str) -> int:
    """
    Determine the tier of a model based on its ID.
    
    Tier 1: Priority models (Claude Sonnet/Opus, Gemini Pro/Flash, GPT-5*,
            GLM, Qwen3-Coder, MiniMax, Kimi-K2)
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
    Get search terms for a model using the global MODEL_ALIASES map.
    
    This is a simple wrapper around get_model_aliases() for backward compatibility.
    Only returns exact aliases - no pattern matching or substring expansion.
    
    Args:
        model_id: The canonical model ID
        
    Returns:
        List of all known names for this model
    """
    return get_model_aliases(model_id)


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
    
    This is a simple wrapper around get_model_aliases() for backward compatibility.
    Returns terms that should match as JSON keys in the model prices file.
    
    Args:
        model_id: The canonical model ID
        
    Returns:
        List of all known names for this model
    """
    return get_model_aliases(model_id)


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


def _extract_saas_model_names(payload) -> Optional[list[str]]:
    """Extract openhands-provider model identifiers from SaaS API responses.

    The tracker is interested in whether a model shows up in the dropdown's
    openhands provider — including both the "Verified" subsection (models
    the SDK has hardcoded as verified) and the "Others" subsection (DB
    entries the SDK doesn't yet recognise).  Both subsections are loaded
    from the same SaaS DB query, just split client-side by the ``verified``
    flag, so we treat them uniformly here.

    Supported response shapes:

    * Plain JSON list (legacy / mock convenience).
    * ``ModelsResponse`` from ``/api/options/models``: prefer the
      ``verified_models`` field, which holds the bare openhands-provider
      names (regardless of their ``verified`` flag in the dropdown).
      Fall through to ``models`` only if ``verified_models`` is absent.
    * ``LLMModelPage`` from ``/api/v1/config/models/search``: an
      ``items`` list of ``{provider, name, verified}`` dicts.  The caller
      is expected to constrain the request to the openhands provider via
      ``provider__eq=openhands``; the ``verified`` flag is *not* used as
      a filter so that "Others"-section entries are included too.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, str)]

    if isinstance(payload, dict):
        # ``verified_models`` is the bare-name list of the openhands
        # provider's DB entries; it intentionally includes both verified
        # and other entries from the dropdown's perspective.
        if isinstance(payload.get("verified_models"), list):
            return [item for item in payload["verified_models"] if isinstance(item, str)]

        if isinstance(payload.get("models"), list):
            return [item for item in payload["models"] if isinstance(item, str)]

        if isinstance(payload.get("items"), list):
            models = []
            for item in payload["items"]:
                if not isinstance(item, dict):
                    continue
                provider = item.get("provider")
                name = item.get("name")
                if provider and name:
                    models.append(f"{provider}/{name}")
                elif name:
                    models.append(name)
            return models

    return None


def _fetch_json_payload(url: str, headers: dict, params: dict | None = None):
    """Fetch JSON from a SaaS endpoint, rejecting HTML/app-shell responses."""
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type and not response.text.lstrip().startswith(("[", "{")):
        raise ValueError(
            f"non-JSON response from {response.url} ({content_type or 'unknown content-type'})"
        )

    return response.json()


def _fetch_saas_models_v1(headers: dict) -> list[str]:
    """Fetch the openhands-provider model catalog from the v1 config API.

    The frontend's model selector renders openhands-provider models in two
    subsections (see ``frontend/src/components/shared/modals/settings/model-selector.tsx``
    in the OpenHands repo):

    * **Verified** — entries flagged ``verified: true`` (those listed in
      the SDK's ``VERIFIED_OPENHANDS_MODELS``).
    * **Others** — entries flagged ``verified: false`` (DB-loaded models
      the SDK doesn't yet know about).

    Both subsections are user-selectable, so we deliberately do *not*
    pass ``verified__eq``: the unfiltered ``provider__eq=openhands`` query
    returns the full openhands-provider list — verified plus "Others".
    """
    models: list[str] = []
    page_id = None

    for _ in range(20):
        params: dict[str, str | int] = {"provider__eq": "openhands", "limit": 100}
        if page_id:
            params["page_id"] = page_id

        payload = _fetch_json_payload(
            "https://app.all-hands.dev/api/v1/config/models/search",
            headers,
            params=params,
        )
        page_models = _extract_saas_model_names(payload)
        if page_models is None:
            raise ValueError("unsupported JSON payload shape from /api/v1/config/models/search")

        models.extend(page_models)

        if not isinstance(payload, dict):
            break
        page_id = payload.get("next_page_id")
        if not page_id:
            break
    else:
        raise ValueError("too many pages returned from /api/v1/config/models/search")

    return models


# Process-wide cache for the SaaS model catalog.  The dropdown is the same
# for every model we track in a single run, so fetching it once is enough.
_saas_models_cache: dict = {"models": None, "failed": False}


def reset_saas_models_cache() -> None:
    """Reset the SaaS model cache (intended for tests)."""
    _saas_models_cache["models"] = None
    _saas_models_cache["failed"] = False


def _fetch_saas_models(*, use_cache: bool = True) -> Optional[list[str]]:
    """Fetch the current SaaS model list, returning None when it cannot be confirmed.

    Uses a process-wide cache so that tracking multiple models in the same
    run doesn't refetch the (potentially large) catalog repeatedly.
    """
    if use_cache:
        cached = _saas_models_cache.get("models")
        if cached is not None:
            return cached
        if _saas_models_cache.get("failed"):
            return None

    api_keys = [
        ("OPENHANDS_CLOUD_API_KEY", os.environ.get("OPENHANDS_CLOUD_API_KEY")),
        ("LLM_API_KEY", os.environ.get("LLM_API_KEY")),
    ]
    api_keys = [(name, value) for name, value in api_keys if value]

    if not api_keys:
        print(
            "Warning: no API key available, cannot confirm SaaS verified models",
            file=sys.stderr,
        )
        if use_cache:
            _saas_models_cache["failed"] = True
        return None

    legacy_urls = [
        "https://app.all-hands.dev/api/options/models",
        "https://app.all-hands.dev/api/public/options/models",
    ]

    last_error = None
    for _key_name, api_key in api_keys:
        headers_list = [
            {"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            {"X-Access-Token": api_key, "Accept": "application/json"},
        ]

        for headers in headers_list:
            try:
                models = _fetch_saas_models_v1(headers)
                if models:
                    if use_cache:
                        _saas_models_cache["models"] = models
                    return models
                last_error = "empty model list from /api/v1/config/models/search"
            except Exception as exc:
                last_error = str(exc)

            for url in legacy_urls:
                try:
                    payload = _fetch_json_payload(url, headers)
                    models = _extract_saas_model_names(payload)
                    if models is not None:
                        if use_cache:
                            _saas_models_cache["models"] = models
                        return models
                    last_error = f"unsupported JSON payload shape from {url}"
                except Exception as exc:
                    last_error = str(exc)
                    continue

    if last_error:
        print(f"Warning: Error checking SaaS verified models: {last_error}", file=sys.stderr)
    if use_cache:
        _saas_models_cache["failed"] = True
    return None


# Aliases starting with these provider-dot prefixes (e.g. ``zai.glm-4.7``,
# ``anthropic.claude-opus-4-6``) are LiteLLM Bedrock-style names that
# belong to a non-openhands provider in the dropdown.  We strip them out
# of the bare-alias set so they can't accidentally collide with an
# openhands-provider entry by sharing a name fragment.
_PROVIDER_DOT_PREFIXES = (
    "anthropic.",
    "minimax.",
    "moonshot.",
    "moonshotai.",
    "nvidia.",
    "qwen.",
    "zai.",
)


def _build_saas_aliases(model_id: str) -> tuple[set[str], set[str]]:
    """Build the (full, bare) lowercase alias sets used for SaaS matching.

    * ``full`` contains every alias as-is (including LiteLLM-style names
      like ``gemini/gemini-3-pro`` and ``zai.glm-4.7``).  Currently
      reserved for callers that need to reason about cross-provider
      aliases; ``check_saas_verified_model`` itself only uses ``bare``.
    * ``bare`` contains the simple model identifiers (no slashes, no
      provider-dot prefix).  These are matched against the openhands
      provider's ``openhands/<name>`` entries — covering both the
      Verified subsection (``verified: true``) and the Others subsection
      (``verified: false``) within the openhands provider.
    """
    full = {model_id.lower()}
    full.update(alias.lower() for alias in get_model_aliases(model_id))

    bare = set()
    for alias in full:
        if "/" in alias:
            continue
        if alias.startswith(_PROVIDER_DOT_PREFIXES):
            continue
        bare.add(alias)

    return full, bare


def check_saas_verified_model(model_id: str) -> Optional[bool]:
    """
    Check if a model appears under the openhands provider in the SaaS dropdown.

    When a user opens the SaaS model selector and picks the "openhands"
    provider, the frontend renders two subsections (see
    ``frontend/src/components/shared/modals/settings/model-selector.tsx`` in
    the OpenHands repo):

    * **Verified** — entries flagged ``verified: true``, i.e. those that
      appear in the SDK's hardcoded ``VERIFIED_OPENHANDS_MODELS`` list.
    * **Others** — entries flagged ``verified: false``, i.e. models that
      have been added to the SaaS verified-models DB but aren't yet in
      the SDK's hardcoded list.

    Both subsections are user-selectable, so for tracker purposes a model
    is "available" in the SaaS dropdown whenever it shows up under the
    openhands provider — regardless of whether it ended up in the
    Verified or the Others bucket.  Previously this function only
    matched aliases against a small allow-list of frontend-style names
    (``-preview`` suffix or 8-digit date suffix), which meant DB entries
    using LiteLLM-style names (e.g. ``glm-4-7-251222``) were missed even
    though they show up in the Others subsection.

    The check only considers openhands-provider entries; non-openhands
    providers (``anthropic``, ``gemini``, etc.) are ignored on purpose —
    they live in a different provider bucket of the dropdown.

    Returns ``True`` when the model is found under openhands (Verified or
    Others), ``False`` when confirmed absent, and ``None`` when the SaaS
    catalog could not be fetched.
    """
    models = _fetch_saas_models()
    if models is None:
        return None

    _, bare_aliases = _build_saas_aliases(model_id)

    for model in models:
        m = model.lower()

        if "/" not in m:
            # Bare name, e.g. from ``/api/options/models``'s
            # ``verified_models`` field.  The SaaS API only emits openhands
            # provider names there, so a match means the model is in the
            # openhands dropdown bucket (verified or other).
            if m in bare_aliases:
                return True
            continue

        # ``provider/name`` form — only match the openhands provider.
        if m.startswith("openhands/"):
            name_part = m[len("openhands/"):]
            if name_part in bare_aliases:
                return True

    return False


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


# Required benchmarks for complete index results
REQUIRED_BENCHMARKS = {"swe-bench", "gaia", "commit0", "swt-bench", "swe-bench-multimodal"}


def search_index_results_for_model(model_id: str) -> Optional[str]:
    """
    Search for when a model's results were FIRST completed in openhands-index-results.
    
    A model is considered complete only when all 5 required benchmarks are present:
    swe-bench, gaia, commit0, swt-bench, swe-bench-multimodal.
    
    Uses local git clone to find the FIRST commit where all required benchmarks were present.

    Args:
        model_id: The language model ID to search for

    Returns:
        ISO timestamp of when results were FIRST completed, or None if incomplete/not found
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
        
        # Check if all required benchmarks are present in current HEAD
        scores_path = os.path.join(results_dir, folder_name, "scores.json")
        if not os.path.exists(scores_path):
            return None
        
        with open(scores_path, "r") as f:
            scores_data = json.load(f)
        
        present_benchmarks = {entry.get("benchmark") for entry in scores_data}
        missing_benchmarks = REQUIRED_BENCHMARKS - present_benchmarks
        
        if missing_benchmarks:
            print(f"Warning: {model_id} missing benchmarks: {missing_benchmarks}", file=sys.stderr)
            return None
        
        # Get ALL commits that modified scores.json, oldest first
        result = subprocess.run(
            ["git", "log", "--format=%H %aI", "--reverse", "--", f"results/{folder_name}/scores.json"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            return None
        
        # Parse commits (oldest first due to --reverse)
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))  # (sha, date)
        
        # Find the FIRST commit where all required benchmarks are present
        scores_file_path = f"results/{folder_name}/scores.json"
        for sha, commit_date in commits:
            # Get file content at this commit
            show_result = subprocess.run(
                ["git", "show", f"{sha}:{scores_file_path}"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if show_result.returncode != 0:
                continue
            
            try:
                commit_scores = json.loads(show_result.stdout)
                commit_benchmarks = {entry.get("benchmark") for entry in commit_scores}
                
                # Check if all required benchmarks are present
                if REQUIRED_BENCHMARKS.issubset(commit_benchmarks):
                    return commit_date
            except (json.JSONDecodeError, TypeError):
                continue
        
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
        "frontend_saas_available": False,
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
    # Note: No adjust_timestamp_to_release - frontend requires explicit model additions
    print(f"Searching for {model_id} in OpenHands frontend...")
    frontend_code_timestamp = search_frontend_for_model(model_id)

    # Check if model is currently available in SaaS verified_models database.
    # This is best-effort: if the live SaaS API cannot be confirmed, keep the
    # self-hosted frontend timestamp instead of regressing known frontend support.
    print(f"Checking if {model_id} is in SaaS verified models...")
    saas_available = check_saas_verified_model(model_id)
    result["frontend_saas_available"] = saas_available is True

    # Frontend support timestamp reflects self-hosted/frontend-code support.
    # SaaS availability is tracked separately in frontend_saas_available.
    result["frontend_support_timestamp"] = frontend_code_timestamp

    # Search for index results using local git clone
    # Note: No adjust_timestamp_to_release - index requires explicit model additions
    print(f"Searching for {model_id} in openhands-index-results...")
    index_timestamp = search_index_results_for_model(model_id)
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
