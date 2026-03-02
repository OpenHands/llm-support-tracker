"""Tests for the LLM support tracking script."""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from track_llm_support import (
    adjust_frontend_to_sdk_timestamp,
    get_github_headers,
    search_commits_for_model,
    search_index_results_folder,
    search_infra_proxy,
    search_litellm_support,
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


class TestSearchLitellmSupport:
    """Tests for search_litellm_support function."""

    @patch("track_llm_support.requests.get")
    def test_search_litellm_success(self, mock_get):
        """Test successful litellm search using binary search through commits."""
        def mock_response_factory(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            if 'raw.githubusercontent.com' in url:
                # Return file content with the model
                mock_response.text = '{"test-model": {"price": 0.01}}'
            elif '/commits' in url:
                # Return list of commits
                mock_response.json.return_value = [
                    {"sha": "abc123", "commit": {"author": {"date": "2024-01-15T10:00:00Z"}}},
                    {"sha": "def456", "commit": {"author": {"date": "2024-01-10T10:00:00Z"}}},
                ]
            return mock_response
        
        mock_get.side_effect = mock_response_factory

        result = search_litellm_support("test-model")
        # Should find the model in the oldest commit checked
        assert result is not None

    @patch("track_llm_support.requests.get")
    def test_search_litellm_not_found(self, mock_get):
        """Test litellm search when model is not found in current version."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"other-model": {"price": 0.01}}'  # Model not in file
        mock_get.return_value = mock_response

        result = search_litellm_support("nonexistent-model")
        assert result is None


class TestSearchInfraProxy:
    """Tests for search_infra_proxy function."""

    @patch("track_llm_support.requests.get")
    def test_search_eval_proxy_success(self, mock_get):
        """Test successful eval proxy search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # The new implementation uses commits API which returns a list of commits
        mock_response.json.return_value = [
            {
                "commit": {
                    "message": "Add test-model to eval proxy",
                    "author": {"date": "2024-01-15T10:00:00Z"}
                }
            },
            {
                "commit": {
                    "message": "Initial commit",
                    "author": {"date": "2024-01-10T10:00:00Z"}
                }
            }
        ]
        mock_get.return_value = mock_response

        result = search_infra_proxy("test-model", "eval_proxy")
        assert result == "2024-01-15T10:00:00Z"

    @patch("track_llm_support.requests.get")
    def test_search_prod_proxy_not_found(self, mock_get):
        """Test prod proxy search when model is not found and no wildcards match."""
        import base64
        
        def mock_response_factory(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            if '/commits' in url:
                # Return commits that don't mention the model
                mock_response.json.return_value = [
                    {
                        "commit": {
                            "message": "Add other-model to prod proxy",
                            "author": {"date": "2024-01-15T10:00:00Z"}
                        }
                    }
                ]
            elif '/contents' in url:
                # Return file content without any wildcards
                mock_response.json.return_value = {
                    "content": base64.b64encode(b"model_list: []").decode()
                }
            return mock_response
        
        mock_get.side_effect = mock_response_factory

        result = search_infra_proxy("nonexistent-model", "prod_proxy")
        assert result is None


class TestAdjustFrontendToSdkTimestamp:
    """Tests for adjust_frontend_to_sdk_timestamp function."""

    def test_frontend_after_sdk_unchanged(self):
        """Test that frontend timestamp after SDK is unchanged."""
        frontend = "2024-01-25T10:00:00Z"
        sdk = "2024-01-20T10:00:00Z"
        result = adjust_frontend_to_sdk_timestamp(frontend, sdk)
        assert result == frontend

    def test_frontend_before_sdk_adjusted(self):
        """Test that frontend timestamp before SDK is adjusted to SDK timestamp."""
        frontend = "2024-01-15T10:00:00Z"
        sdk = "2024-01-20T10:00:00Z"
        result = adjust_frontend_to_sdk_timestamp(frontend, sdk)
        assert result == sdk

    def test_frontend_none_returns_none(self):
        """Test that None frontend returns None."""
        result = adjust_frontend_to_sdk_timestamp(None, "2024-01-20T10:00:00Z")
        assert result is None

    def test_sdk_none_returns_frontend(self):
        """Test that None SDK returns frontend unchanged."""
        frontend = "2024-01-15T10:00:00Z"
        result = adjust_frontend_to_sdk_timestamp(frontend, None)
        assert result == frontend

    def test_both_none_returns_none(self):
        """Test that both None returns None."""
        result = adjust_frontend_to_sdk_timestamp(None, None)
        assert result is None

    def test_different_timezone_formats(self):
        """Test that different timezone formats are handled correctly."""
        # Frontend is before SDK when normalized to same timezone
        frontend = "2025-12-01T00:00:00Z"
        sdk = "2025-12-20T05:32:55.000-08:00"
        result = adjust_frontend_to_sdk_timestamp(frontend, sdk)
        assert result == sdk

    def test_same_timestamp_unchanged(self):
        """Test that same timestamps return frontend unchanged."""
        timestamp = "2024-01-20T10:00:00Z"
        result = adjust_frontend_to_sdk_timestamp(timestamp, timestamp)
        assert result == timestamp


class TestTrackLlmSupport:
    """Tests for track_llm_support function."""

    @patch("track_llm_support.search_litellm_support")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    def test_track_llm_support_all_found(
        self, mock_search_commits, mock_search_index, mock_search_infra, mock_search_litellm
    ):
        """Test tracking when model is found in all repositories."""
        mock_search_commits.side_effect = [
            "2024-01-20T10:00:00Z",  # SDK
            "2024-01-25T10:00:00Z",  # Frontend
        ]
        mock_search_index.return_value = "2024-02-05T10:00:00Z"
        mock_search_infra.side_effect = [
            "2024-02-01T10:00:00Z",  # Eval proxy
            "2024-02-03T10:00:00Z",  # Prod proxy
        ]
        mock_search_litellm.return_value = "2024-01-18T10:00:00Z"

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["release_date"] == "2024-01-15"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] == "2024-01-25T10:00:00Z"
        assert result["eval_proxy_timestamp"] == "2024-02-01T10:00:00Z"
        assert result["prod_proxy_timestamp"] == "2024-02-03T10:00:00Z"
        assert result["index_results_timestamp"] == "2024-02-05T10:00:00Z"
        assert result["litellm_support_timestamp"] == "2024-01-18T10:00:00Z"

    @patch("track_llm_support.search_litellm_support")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    def test_track_llm_support_partial(
        self, mock_search_commits, mock_search_index, mock_search_infra, mock_search_litellm
    ):
        """Test tracking when model is only found in some repositories."""
        mock_search_commits.side_effect = [
            "2024-01-20T10:00:00Z",  # SDK
            None,  # Frontend
        ]
        mock_search_index.return_value = None
        mock_search_infra.side_effect = [None, None]  # Eval and Prod proxy
        mock_search_litellm.return_value = None

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] is None
        assert result["eval_proxy_timestamp"] is None
        assert result["prod_proxy_timestamp"] is None
        assert result["index_results_timestamp"] is None
        assert result["litellm_support_timestamp"] is None

    @patch("track_llm_support.search_litellm_support")
    @patch("track_llm_support.search_infra_proxy")
    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    def test_track_llm_support_frontend_before_sdk_adjusted(
        self, mock_search_commits, mock_search_index, mock_search_infra, mock_search_litellm
    ):
        """Test that frontend timestamp before SDK is adjusted to SDK timestamp.
        
        This tests the fix for issue #5: DeepSeek-V3.2-Reasoner had frontend support
        timestamp (2025-12-01) before SDK support (2025-12-20), which is incorrect
        since frontend depends on SDK support.
        """
        mock_search_commits.side_effect = [
            "2024-01-20T10:00:00Z",  # SDK
            "2024-01-15T10:00:00Z",  # Frontend (incorrectly before SDK)
        ]
        mock_search_index.return_value = None
        mock_search_infra.side_effect = [None, None]
        mock_search_litellm.return_value = None

        result = track_llm_support("test-model", "2024-01-10")

        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        # Frontend should be adjusted to SDK timestamp since it can't be before
        assert result["frontend_support_timestamp"] == "2024-01-20T10:00:00Z"


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
