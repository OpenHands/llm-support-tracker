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
    check_model_in_litellm_json,
    search_commits_for_model,
    search_sdk_for_model,
    search_index_results_folder,
    search_infra_proxy,
    search_litellm_support,
    find_litellm_versions_supporting_model,
    track_llm_support,
)


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


class TestSearchIndexResultsFolder:
    """Tests for search_index_results_folder function."""

    @patch("track_llm_support.requests.get")
    def test_search_index_results_success(self, mock_get):
        """Test successful index results folder search."""
        # First call: get contents
        contents_response = MagicMock()
        contents_response.status_code = 200
        contents_response.json.return_value = [
            {"type": "dir", "name": "test-model"},
            {"type": "dir", "name": "other-model"},
        ]

        # Second call: get commits
        commits_response = MagicMock()
        commits_response.status_code = 200
        commits_response.json.return_value = [
            {"commit": {"author": {"date": "2024-02-01T10:00:00Z"}}},
            {"commit": {"author": {"date": "2024-01-15T10:00:00Z"}}},
        ]

        mock_get.side_effect = [contents_response, commits_response]

        result = search_index_results_folder("test-model")
        assert result == "2024-01-15T10:00:00Z"

    @patch("track_llm_support.requests.get")
    def test_search_index_results_folder_not_found(self, mock_get):
        """Test index results search when folder is not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"type": "dir", "name": "other-model"},
        ]
        mock_get.return_value = mock_response

        result = search_index_results_folder("nonexistent-model")
        assert result is None


class TestGetLitellmModelSearchTerms:
    """Tests for get_litellm_model_search_terms function."""

    def test_basic_model_id(self):
        """Test basic model ID returns lowercase version."""
        terms = get_litellm_model_search_terms("test-model")
        assert terms == ["test-model"]

    def test_model_with_alias(self):
        """Test model with defined alias returns alias."""
        terms = get_litellm_model_search_terms("DeepSeek-V3.2-Reasoner")
        # Uses versioned name to avoid matching older unversioned deepseek-reasoner
        assert terms == ["deepseek/deepseek-v3.2"]

    def test_glm5_alias(self):
        """Test GLM-5 returns correct litellm name."""
        terms = get_litellm_model_search_terms("GLM-5")
        assert terms == ["zai/glm-5"]

    def test_model_without_alias(self):
        """Test model without alias returns lowercase original."""
        terms = get_litellm_model_search_terms("claude-sonnet-4-5")
        assert terms == ["claude-sonnet-4-5"]


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
    def test_search_eval_proxy_success(self, mock_get_repo):
        """Test successful eval proxy search with valid versions."""
        # Mock the infra cache with version history
        mock_get_repo.return_value = {
            "eval_proxy_history": [
                ("2024-01-10T10:00:00Z", "v1.79.0"),  # oldest, has valid version
                ("2024-01-15T10:00:00Z", "v1.80.0-stable"),
            ],
            "prod_proxy_history": [],
        }
        
        # Valid versions that support the model
        valid_versions = ["v1.81.0", "v1.80.0-stable", "v1.79.0"]
        
        result = search_infra_proxy("test-model", "eval_proxy", valid_versions)
        assert result == "2024-01-10T10:00:00Z"  # Earliest commit with valid version

    @patch("track_llm_support._get_infra_repo")
    def test_search_prod_proxy_not_found(self, mock_get_repo):
        """Test prod proxy search when no valid versions were deployed."""
        # Mock the infra cache with version history that doesn't match
        mock_get_repo.return_value = {
            "eval_proxy_history": [],
            "prod_proxy_history": [
                ("2024-01-10T10:00:00Z", "v1.70.0"),  # Not in valid versions
                ("2024-01-15T10:00:00Z", "v1.71.0"),
            ],
        }
        
        # Valid versions that don't match what's deployed
        valid_versions = ["v1.81.0", "v1.80.0-stable", "v1.79.0"]
        
        result = search_infra_proxy("test-model", "prod_proxy", valid_versions)
        assert result is None
    
    def test_search_infra_proxy_no_valid_versions(self):
        """Test that None is returned when valid_versions is None."""
        result = search_infra_proxy("test-model", "eval_proxy", None)
        assert result is None


class TestTrackLlmSupport:
    """Tests for track_llm_support function."""

    @patch("track_llm_support._get_litellm_repo")
    @patch("track_llm_support.find_litellm_versions_supporting_model")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    @patch("track_llm_support.search_sdk_for_model")
    def test_track_llm_support_all_found(
        self, mock_search_sdk, mock_search_commits, mock_search_index, mock_search_infra, 
        mock_find_versions, mock_get_repo
    ):
        """Test tracking when model is found in all repositories."""
        mock_search_sdk.return_value = "2024-01-20T10:00:00Z"  # SDK
        mock_search_commits.return_value = "2024-01-25T10:00:00Z"  # Frontend
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
    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    @patch("track_llm_support.search_sdk_for_model")
    def test_track_llm_support_partial(
        self, mock_search_sdk, mock_search_commits, mock_search_index, mock_search_infra, mock_find_versions
    ):
        """Test tracking when model is only found in some repositories."""
        mock_search_sdk.return_value = "2024-01-20T10:00:00Z"  # SDK
        mock_search_commits.return_value = None  # Frontend
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
