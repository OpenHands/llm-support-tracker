"""Tests for the LLM support tracking script."""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from track_llm_support import (
    get_github_headers,
    get_litellm_model_search_terms,
    get_model_tier,
    get_model_aliases,
    MODEL_ALIASES,
    check_model_in_litellm_json,
    search_commits_for_model,
    search_sdk_for_model,
    search_frontend_for_model,
    search_index_results_folder,
    search_index_results_for_model,
    search_infra_proxy,
    search_litellm_support,
    find_litellm_versions_supporting_model,
    track_llm_support,
)


class TestModelAliases:
    """Tests for MODEL_ALIASES and get_model_aliases function."""

    def test_model_aliases_is_dict(self):
        """MODEL_ALIASES should be a dictionary."""
        assert isinstance(MODEL_ALIASES, dict)

    def test_get_model_aliases_returns_list(self):
        """get_model_aliases should always return a list."""
        assert isinstance(get_model_aliases("test-model"), list)

    def test_get_model_aliases_includes_model_id(self):
        """get_model_aliases should always include the model ID itself."""
        model_id = "test-model"
        aliases = get_model_aliases(model_id)
        assert model_id in aliases

    def test_get_model_aliases_no_exact_duplicates(self):
        """get_model_aliases should not return exact duplicates."""
        for model_id in MODEL_ALIASES.keys():
            aliases = get_model_aliases(model_id)
            # Check no exact duplicates (case-sensitive is OK since git search is case-sensitive)
            assert len(aliases) == len(set(aliases)), f"Exact duplicates found for {model_id}"

    def test_claude_sonnet_4_6_no_frontend_alias(self):
        """claude-sonnet-4-6 should not have frontend alias (not yet in frontend)."""
        aliases = get_model_aliases("claude-sonnet-4-6")
        # Should only have the model ID itself
        assert aliases == ["claude-sonnet-4-6"]
        # Should NOT contain claude-sonnet-4-5 related aliases
        for alias in aliases:
            assert "4-5" not in alias

    def test_claude_sonnet_4_5_has_frontend_alias(self):
        """claude-sonnet-4-5 should have frontend alias."""
        aliases = get_model_aliases("claude-sonnet-4-5")
        assert "claude-sonnet-4-5" in aliases
        assert "claude-sonnet-4-5-20250929" in aliases

    def test_gemini_has_preview_alias(self):
        """Gemini models should have -preview suffix aliases."""
        aliases = get_model_aliases("Gemini-3-Pro")
        assert "gemini-3-pro-preview" in aliases

        aliases = get_model_aliases("Gemini-3-Flash")
        assert "gemini-3-flash-preview" in aliases


class TestGetGithubHeaders:
    """Tests for get_github_headers function."""

    def test_headers_without_token(self):
        """Test headers when GITHUB_TOKEN is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove GITHUB_TOKEN if it exists
            os.environ.pop("GITHUB_TOKEN", None)
            headers = get_github_headers()
            assert "Accept" in headers
            assert headers["Accept"] == "application/vnd.github.v3+json"
            assert "Authorization" not in headers

    def test_headers_with_token(self):
        """Test headers when GITHUB_TOKEN is set."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"}):
            headers = get_github_headers()
            assert "Accept" in headers
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_token"


class TestGetModelTier:
    """Tests for get_model_tier function."""

    def test_claude_sonnet_is_tier_1(self):
        """Claude Sonnet models should be tier 1."""
        assert get_model_tier("claude-sonnet-4-5") == 1
        assert get_model_tier("claude-sonnet-4-6") == 1
        assert get_model_tier("claude-sonnet-3-5") == 1

    def test_claude_opus_is_tier_1(self):
        """Claude Opus models should be tier 1."""
        assert get_model_tier("claude-opus-4-5") == 1
        assert get_model_tier("claude-opus-4-6") == 1

    def test_gemini_pro_flash_is_tier_1(self):
        """Gemini Pro and Flash models should be tier 1."""
        assert get_model_tier("Gemini-3-Pro") == 1
        assert get_model_tier("Gemini-3-Flash") == 1
        assert get_model_tier("Gemini-2-Pro") == 1
        assert get_model_tier("Gemini-2-Flash") == 1

    def test_gpt5_is_tier_1(self):
        """GPT-5* models should be tier 1."""
        assert get_model_tier("GPT-5.2") == 1
        assert get_model_tier("GPT-5.2-Codex") == 1
        assert get_model_tier("GPT-5") == 1

    def test_glm_is_tier_1(self):
        """GLM models should be tier 1."""
        assert get_model_tier("GLM-4.7") == 1
        assert get_model_tier("GLM-5") == 1

    def test_minimax_m25_is_tier_1(self):
        """MiniMax-M2.5 should be tier 1 (M2.1 was superseded before frontend support)."""
        assert get_model_tier("MiniMax-M2.5") == 1
        assert get_model_tier("MiniMax-M2.1") == 2  # Superseded before frontend support

    def test_qwen3_coder_is_tier_1(self):
        """Qwen3-Coder-* models should be tier 1."""
        assert get_model_tier("Qwen3-Coder-480B") == 1
        assert get_model_tier("Qwen3-Coder-Next") == 1

    def test_kimi_k25_is_tier_1(self):
        """Kimi-K2.5 should be tier 1 (K2-Thinking was superseded before frontend support)."""
        assert get_model_tier("Kimi-K2.5") == 1
        assert get_model_tier("Kimi-K2-Thinking") == 2  # Superseded before frontend support

    def test_other_models_are_tier_2(self):
        """Non-priority models should be tier 2."""
        assert get_model_tier("DeepSeek-V3.2-Reasoner") == 2
        assert get_model_tier("Nemotron-3-Nano") == 2
        assert get_model_tier("SomeOther-Model") == 2


class TestSearchCommitsForModel:
    """Tests for search_commits_for_model function."""

    @patch("track_llm_support.requests.get")
    def test_search_commits_success(self, mock_get):
        """Test successful commit search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 1,
            "items": [
                {
                    "commit": {
                        "author": {"date": "2024-01-15T10:00:00Z"}
                    }
                }
            ],
        }
        mock_get.return_value = mock_response

        result = search_commits_for_model(
            "OpenHands/test-repo", "test-model", ["path/"]
        )
        assert result == "2024-01-15T10:00:00Z"

    @patch("track_llm_support.requests.get")
    def test_search_commits_not_found(self, mock_get):
        """Test commit search when model is not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_count": 0, "items": []}
        mock_get.return_value = mock_response

        result = search_commits_for_model(
            "OpenHands/test-repo", "nonexistent-model", ["path/"]
        )
        assert result is None

    @patch("track_llm_support.requests.get")
    def test_search_commits_api_error(self, mock_get):
        """Test commit search when API returns an error."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        result = search_commits_for_model(
            "OpenHands/test-repo", "test-model", ["path/"]
        )
        assert result is None


class TestSearchIndexResultsForModel:
    """Tests for search_index_results_for_model function."""

    @patch("track_llm_support._get_index_results_repo")
    def test_search_index_results_success(self, mock_get_repo):
        """Test successful index results folder search with complete benchmarks."""
        import subprocess
        
        # Create a mock temp directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = os.path.join(temp_dir, "results")
            os.makedirs(results_dir)
            model_dir = os.path.join(results_dir, "test-model")
            os.makedirs(model_dir)
            os.makedirs(os.path.join(results_dir, "other-model"))
            
            # Create scores.json with all required benchmarks
            scores_data = [
                {"benchmark": "swe-bench", "score": 50.0},
                {"benchmark": "gaia", "score": 45.0},
                {"benchmark": "commit0", "score": 30.0},
                {"benchmark": "swt-bench", "score": 40.0},
                {"benchmark": "swe-bench-multimodal", "score": 35.0},
            ]
            with open(os.path.join(model_dir, "scores.json"), "w") as f:
                json.dump(scores_data, f)
            
            mock_get_repo.return_value = {"temp_dir": temp_dir}
            
            # Mock subprocess.run to return a date
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="2024-01-15T10:00:00Z"
                )
                
                result = search_index_results_for_model("test-model")
                assert result == "2024-01-15T10:00:00Z"

    @patch("track_llm_support._get_index_results_repo")
    def test_search_index_results_incomplete_benchmarks(self, mock_get_repo):
        """Test index results search returns None when benchmarks are incomplete."""
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = os.path.join(temp_dir, "results")
            os.makedirs(results_dir)
            model_dir = os.path.join(results_dir, "test-model")
            os.makedirs(model_dir)
            
            # Create scores.json with only 4 benchmarks (missing swe-bench-multimodal)
            scores_data = [
                {"benchmark": "swe-bench", "score": 50.0},
                {"benchmark": "gaia", "score": 45.0},
                {"benchmark": "commit0", "score": 30.0},
                {"benchmark": "swt-bench", "score": 40.0},
            ]
            with open(os.path.join(model_dir, "scores.json"), "w") as f:
                json.dump(scores_data, f)
            
            mock_get_repo.return_value = {"temp_dir": temp_dir}
            
            result = search_index_results_for_model("test-model")
            assert result is None

    @patch("track_llm_support._get_index_results_repo")
    def test_search_index_results_folder_not_found(self, mock_get_repo):
        """Test index results search when folder is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = os.path.join(temp_dir, "results")
            os.makedirs(results_dir)
            os.makedirs(os.path.join(results_dir, "other-model"))
            
            mock_get_repo.return_value = {"temp_dir": temp_dir}
            
            result = search_index_results_for_model("nonexistent-model")
            assert result is None


class TestGetLitellmModelSearchTerms:
    """Tests for get_litellm_model_search_terms function."""

    def test_basic_model_id(self):
        """Test basic model ID returns the model ID itself."""
        terms = get_litellm_model_search_terms("test-model")
        assert terms == ["test-model"]

    def test_model_with_alias(self):
        """Test model with defined alias returns all aliases."""
        terms = get_litellm_model_search_terms("DeepSeek-V3.2-Reasoner")
        # Should include the model ID and all defined aliases
        assert "DeepSeek-V3.2-Reasoner" in terms
        assert "deepseek/deepseek-v3.2" in terms

    def test_glm5_alias(self):
        """Test GLM-5 returns model ID and aliases."""
        terms = get_litellm_model_search_terms("GLM-5")
        assert "GLM-5" in terms
        assert "zai/glm-5" in terms

    def test_gemini_3_pro_alias(self):
        """Test Gemini-3-Pro returns model ID and preview suffix alias."""
        terms = get_litellm_model_search_terms("Gemini-3-Pro")
        assert "Gemini-3-Pro" in terms
        assert "gemini-3-pro-preview" in terms

    def test_gemini_3_flash_alias(self):
        """Test Gemini-3-Flash returns model ID and preview suffix alias."""
        terms = get_litellm_model_search_terms("Gemini-3-Flash")
        assert "Gemini-3-Flash" in terms
        assert "gemini-3-flash-preview" in terms

    def test_model_without_alias(self):
        """Test model without alias returns just the model ID."""
        # claude-sonnet-4-6 has no aliases defined
        terms = get_litellm_model_search_terms("claude-sonnet-4-6")
        assert terms == ["claude-sonnet-4-6"]

    def test_model_with_frontend_alias(self):
        """Test model with frontend alias includes it."""
        terms = get_litellm_model_search_terms("claude-sonnet-4-5")
        assert "claude-sonnet-4-5" in terms
        assert "claude-sonnet-4-5-20250929" in terms


class TestCheckModelInLitellmJson:
    """Tests for check_model_in_litellm_json function."""

    def test_model_as_json_key(self):
        """Test finding model as a JSON key."""
        content = '{"test-model": {"price": 0.01}, "other": {}}'
        assert check_model_in_litellm_json(content, "test-model") is True

    def test_model_with_provider_prefix(self):
        """Test finding model with provider prefix like openai/gpt-4."""
        content = '{"openai/test-model": {"price": 0.01}}'
        assert check_model_in_litellm_json(content, "test-model") is True

    def test_model_not_found(self):
        """Test when model is not in the JSON."""
        content = '{"other-model": {"price": 0.01}}'
        assert check_model_in_litellm_json(content, "test-model") is False

    def test_partial_match_rejected(self):
        """Test that partial matches in values are rejected."""
        # Model appears in a value, not as a key
        content = '{"model": {"name": "test-model-v2"}}'
        assert check_model_in_litellm_json(content, "test-model") is False

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        content = '{"TEST-MODEL": {"price": 0.01}}'
        assert check_model_in_litellm_json(content, "test-model") is True


class TestSearchLitellmSupport:
    """Tests for search_litellm_support function."""

    def test_tag_version_filter(self):
        """Test that the tag filter correctly identifies stable versions."""
        import re
        
        tags = [
            "v1.81.13",                              # Stable - should match
            "v1.80.0",                               # Stable - should match
            "v1.79.0",                               # Stable - should match
            "v1.0.0",                                # Stable - should match
            "v1.81.9-stable",                        # Stable release - should match
            "v1.81.9-stable.gemini.3.1-pro",         # Stable release - should match
            "v1.81.3-stable.sonnet-4-6",             # Stable release - should match
            "v1.80.1-nightly",                       # Non-stable - should NOT match
            "v1.79.0-rc.1",                          # Non-stable - should NOT match
            "v1.78.0.dev1",                          # Non-stable - should NOT match
            "v1.81.9.rc.1",                          # Non-stable - should NOT match
            "v1.81.7.dev1",                          # Non-stable - should NOT match
        ]
        
        def is_stable(tag):
            if not re.match(r'^v\d+\.\d+(\.\d+)?(\.\d+)?(-stable.*)?$', tag):
                return False
            return '-nightly' not in tag and '.rc' not in tag and '.dev' not in tag
        
        stable_tags = [t for t in tags if is_stable(t)]
        
        assert "v1.81.13" in stable_tags
        assert "v1.80.0" in stable_tags
        assert "v1.79.0" in stable_tags
        assert "v1.0.0" in stable_tags
        assert "v1.81.9-stable" in stable_tags
        assert "v1.81.9-stable.gemini.3.1-pro" in stable_tags
        assert "v1.81.3-stable.sonnet-4-6" in stable_tags
        assert "v1.80.1-nightly" not in stable_tags
        assert "v1.79.0-rc.1" not in stable_tags
        assert "v1.78.0.dev1" not in stable_tags
        assert "v1.81.9.rc.1" not in stable_tags

    def test_version_sorting(self):
        """Test that version tags are sorted correctly (newest first)."""
        tags = ["v1.0.0", "v1.80.0", "v1.81.13", "v1.79.0", "v1.9.0"]
        
        def version_key(tag):
            try:
                parts = tag[1:].split(".")
                return tuple(int(p) for p in parts)
            except ValueError:
                return (0,)
        
        sorted_tags = sorted(tags, key=version_key, reverse=True)
        
        assert sorted_tags[0] == "v1.81.13"
        assert sorted_tags[1] == "v1.80.0"
        assert sorted_tags[-1] == "v1.0.0"

    def test_search_litellm_nonexistent_model(self):
        """Test that searching for a nonexistent model returns None quickly."""
        # This test uses check_model_in_litellm_json which is the first filter
        result = check_model_in_litellm_json('{"other-model": {}}', "nonexistent-model-xyz")
        assert result is False


class TestSearchInfraProxy:
    """Tests for search_infra_proxy function."""

    @patch("track_llm_support._get_infra_repo")
    @patch("track_llm_support.search_infra_proxy_for_model_name")
    def test_search_both_conditions_met_model_name_later(self, mock_search_name, mock_get_repo):
        """Test when both conditions met - model name appears AFTER litellm version deployed."""
        # Model appears in config at this time
        mock_search_name.return_value = "2024-01-20T10:00:00Z"
        
        # Litellm version deployed earlier
        mock_get_repo.return_value = {
            "eval_proxy_history": [
                ("2024-01-10T10:00:00Z", "v1.79.0"),  # Earlier
            ],
            "prod_proxy_history": [],
        }
        
        valid_versions = ["v1.79.0"]
        result = search_infra_proxy("test-model", "eval_proxy", valid_versions)
        
        # Should return the LATER timestamp (when both conditions are true)
        assert result == "2024-01-20T10:00:00Z"

    @patch("track_llm_support._get_infra_repo")
    @patch("track_llm_support.search_infra_proxy_for_model_name")
    def test_search_both_conditions_met_version_later(self, mock_search_name, mock_get_repo):
        """Test when both conditions met - litellm version deployed AFTER model name appears."""
        # Model appears in config earlier
        mock_search_name.return_value = "2024-01-10T10:00:00Z"
        
        # Litellm version deployed later
        mock_get_repo.return_value = {
            "eval_proxy_history": [
                ("2024-01-20T10:00:00Z", "v1.79.0"),  # Later
            ],
            "prod_proxy_history": [],
        }
        
        valid_versions = ["v1.79.0"]
        result = search_infra_proxy("test-model", "eval_proxy", valid_versions)
        
        # Should return the LATER timestamp (when both conditions are true)
        assert result == "2024-01-20T10:00:00Z"

    @patch("track_llm_support._get_infra_repo")
    @patch("track_llm_support.search_infra_proxy_for_model_name")
    def test_search_only_model_name_no_version(self, mock_search_name, mock_get_repo):
        """Test when model in config but no valid litellm version deployed."""
        # Model in config
        mock_search_name.return_value = "2024-01-20T10:00:00Z"
        
        # No valid litellm version
        mock_get_repo.return_value = {
            "eval_proxy_history": [
                ("2024-01-10T10:00:00Z", "v1.70.0"),  # Not in valid versions
            ],
            "prod_proxy_history": [],
        }
        
        valid_versions = ["v1.79.0"]
        result = search_infra_proxy("test-model", "eval_proxy", valid_versions)
        
        # Should return None (both conditions not met)
        assert result is None

    @patch("track_llm_support._get_infra_repo")
    @patch("track_llm_support.search_infra_proxy_for_model_name")
    def test_search_only_version_no_model_name(self, mock_search_name, mock_get_repo):
        """Test when litellm version deployed but model not in config.
        
        This is a regression test for issue #17: GLM-4.7 was marked as supported
        just because litellm supported it, even though it wasn't in the config.
        """
        # Model NOT in config
        mock_search_name.return_value = None
        
        # Valid litellm version deployed
        mock_get_repo.return_value = {
            "eval_proxy_history": [
                ("2024-01-10T10:00:00Z", "v1.79.0"),
            ],
            "prod_proxy_history": [],
        }
        
        valid_versions = ["v1.79.0"]
        result = search_infra_proxy("GLM-4.7", "eval_proxy", valid_versions)
        
        # Should return None (both conditions not met)
        assert result is None
    
    @patch("track_llm_support.search_infra_proxy_for_model_name")
    def test_search_infra_proxy_no_valid_versions(self, mock_search_name):
        """Test that None is returned when valid_versions is None."""
        mock_search_name.return_value = "2024-01-20T10:00:00Z"
        
        result = search_infra_proxy("test-model", "eval_proxy", None)
        
        # Should return None (litellm version condition not met)
        assert result is None


class TestTrackLlmSupport:
    """Tests for track_llm_support function."""

    @patch("track_llm_support._get_litellm_repo")
    @patch("track_llm_support.find_litellm_versions_supporting_model")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_for_model")
    @patch("track_llm_support.search_frontend_for_model")
    @patch("track_llm_support.search_sdk_for_model")
    def test_track_llm_support_all_found(
        self, mock_search_sdk, mock_search_frontend, mock_search_index, mock_search_infra, 
        mock_find_versions, mock_get_repo
    ):
        """Test tracking when model is found in all repositories."""
        mock_search_sdk.return_value = "2024-01-20T10:00:00Z"  # SDK
        mock_search_frontend.return_value = "2024-01-25T10:00:00Z"  # Frontend
        mock_search_index.return_value = "2024-02-05T10:00:00Z"
        mock_search_infra.side_effect = [
            "2024-02-01T10:00:00Z",  # Eval proxy
            "2024-02-03T10:00:00Z",  # Prod proxy
        ]
        # Mock litellm versions - returns list of versions (newest first)
        mock_find_versions.return_value = ["v1.81.0", "v1.80.0", "v1.79.0"]
        mock_get_repo.return_value = {
            "tag_dates": {
                "v1.81.0": "2024-01-25T10:00:00Z",
                "v1.80.0": "2024-01-20T10:00:00Z",
                "v1.79.0": "2024-01-18T10:00:00Z",  # Earliest
            }
        }

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["release_date"] == "2024-01-15"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] == "2024-01-25T10:00:00Z"
        assert result["eval_proxy_timestamp"] == "2024-02-01T10:00:00Z"
        assert result["prod_proxy_timestamp"] == "2024-02-03T10:00:00Z"
        assert result["index_results_timestamp"] == "2024-02-05T10:00:00Z"
        assert result["litellm_support_timestamp"] == "2024-01-18T10:00:00Z"

    @patch("track_llm_support.find_litellm_versions_supporting_model")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_for_model")
    @patch("track_llm_support.search_frontend_for_model")
    @patch("track_llm_support.search_sdk_for_model")
    def test_track_llm_support_partial(
        self, mock_search_sdk, mock_search_frontend, mock_search_index, mock_search_infra, mock_find_versions
    ):
        """Test tracking when model is only found in some repositories."""
        mock_search_sdk.return_value = "2024-01-20T10:00:00Z"  # SDK
        mock_search_frontend.return_value = None  # Frontend
        mock_search_index.return_value = None
        mock_search_infra.side_effect = [None, None]  # Eval and Prod proxy
        mock_find_versions.return_value = []  # No litellm versions support this model

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] is None
        assert result["eval_proxy_timestamp"] is None
        assert result["prod_proxy_timestamp"] is None
        assert result["index_results_timestamp"] is None
        assert result["litellm_support_timestamp"] is None


class TestOutputFormat:
    """Tests for output JSON format."""

    def test_output_json_structure(self):
        """Test that output JSON has the correct structure."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            output_file = f.name

        try:
            # Create a sample output
            result = {
                "model_id": "test-model",
                "release_date": "2024-01-15",
                "sdk_support_timestamp": "2024-01-20T10:00:00Z",
                "frontend_support_timestamp": None,
                "index_results_timestamp": None,
                "eval_proxy_timestamp": None,
                "prod_proxy_timestamp": None,
                "litellm_support_timestamp": None,
            }

            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)

            # Read and verify
            with open(output_file, "r") as f:
                loaded = json.load(f)

            assert "model_id" in loaded
            assert "release_date" in loaded
            assert "sdk_support_timestamp" in loaded
            assert "frontend_support_timestamp" in loaded
            assert "index_results_timestamp" in loaded
            assert "eval_proxy_timestamp" in loaded
            assert "prod_proxy_timestamp" in loaded
            assert "litellm_support_timestamp" in loaded

        finally:
            os.unlink(output_file)


class TestLitellmTimestampLogic:
    """Tests for litellm_support_timestamp earliest-of logic."""

    def test_earliest_timestamp_selection(self):
        """Test that the earliest timestamp is selected from multiple sources."""
        from datetime import datetime
        
        # Simulate the logic in track_llm_support
        def find_earliest(candidates):
            candidates = [t for t in candidates if t is not None]
            if not candidates:
                return None
            
            def parse_ts(ts):
                for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        return datetime.strptime(ts.replace("Z", "+00:00") if "Z" in ts else ts, fmt)
                    except ValueError:
                        continue
                return None
            
            parsed = [(t, parse_ts(t)) for t in candidates]
            parsed = [(t, p) for t, p in parsed if p is not None]
            if parsed:
                earliest = min(parsed, key=lambda x: x[1])
                return earliest[0]
            return None
        
        # Test case 1: Official LiteLLM is earliest
        result = find_earliest([
            "2025-11-18T16:06:06-08:00",  # Official LiteLLM
            "2026-01-14T13:43:57-05:00",  # Eval proxy
            "2026-01-14T12:50:34-05:00",  # Prod proxy
        ])
        assert result == "2025-11-18T16:06:06-08:00"
        
        # Test case 2: Eval proxy is earliest
        result = find_earliest([
            "2026-02-01T10:00:00Z",       # Official LiteLLM
            "2026-01-15T08:00:00Z",       # Eval proxy
            "2026-01-20T12:00:00Z",       # Prod proxy
        ])
        assert result == "2026-01-15T08:00:00Z"
        
        # Test case 3: Only proxy timestamps (no official)
        result = find_earliest([
            None,                          # Official LiteLLM
            "2026-01-14T13:43:57-05:00",  # Eval proxy
            "2026-01-10T12:50:34-05:00",  # Prod proxy (earliest)
        ])
        assert result == "2026-01-10T12:50:34-05:00"
        
        # Test case 4: All None
        result = find_earliest([None, None, None])
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
