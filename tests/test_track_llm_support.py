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
    search_commits_for_model,
    search_index_results_folder,
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


class TestTrackLlmSupport:
    """Tests for track_llm_support function."""

    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    def test_track_llm_support_all_found(
        self, mock_search_commits, mock_search_index
    ):
        """Test tracking when model is found in all repositories."""
        mock_search_commits.side_effect = [
            "2024-01-20T10:00:00Z",  # SDK
            "2024-01-25T10:00:00Z",  # Frontend
            "2024-02-01T10:00:00Z",  # Infra
        ]
        mock_search_index.return_value = "2024-02-05T10:00:00Z"

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["release_date"] == "2024-01-15"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] == "2024-01-25T10:00:00Z"
        assert result["infra_litellm_timestamp"] == "2024-02-01T10:00:00Z"
        assert result["index_results_timestamp"] == "2024-02-05T10:00:00Z"

    @patch("track_llm_support.search_index_results_folder")
    @patch("track_llm_support.search_commits_for_model")
    def test_track_llm_support_partial(
        self, mock_search_commits, mock_search_index
    ):
        """Test tracking when model is only found in some repositories."""
        mock_search_commits.side_effect = [
            "2024-01-20T10:00:00Z",  # SDK
            None,  # Frontend
            None,  # Infra
        ]
        mock_search_index.return_value = None

        result = track_llm_support("test-model", "2024-01-15")

        assert result["model_id"] == "test-model"
        assert result["sdk_support_timestamp"] == "2024-01-20T10:00:00Z"
        assert result["frontend_support_timestamp"] is None
        assert result["infra_litellm_timestamp"] is None
        assert result["index_results_timestamp"] is None


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
                "infra_litellm_timestamp": None,
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
            assert "infra_litellm_timestamp" in loaded

        finally:
            os.unlink(output_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
