"""Tests for the data validation script."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from validate_data import parse_timestamp, validate_proxy_after_litellm, validate_data


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_iso_format(self):
        """Test parsing standard ISO format."""
        ts = parse_timestamp("2024-01-15T10:00:00Z")
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15

    def test_parse_with_timezone(self):
        """Test parsing with timezone offset."""
        ts = parse_timestamp("2024-01-15T10:00:00+00:00")
        assert ts is not None
        assert ts.year == 2024

    def test_parse_with_microseconds(self):
        """Test parsing with microseconds."""
        ts = parse_timestamp("2024-01-15T10:00:00.123456Z")
        assert ts is not None
        assert ts.year == 2024

    def test_parse_none(self):
        """Test parsing None returns None."""
        assert parse_timestamp(None) is None

    def test_parse_date_only(self):
        """Test parsing date-only string."""
        ts = parse_timestamp("2024-01-15")
        assert ts is not None
        assert ts.year == 2024


class TestValidateProxyAfterLitellm:
    """Tests for validate_proxy_after_litellm function."""

    def test_valid_order(self):
        """Test when proxy support is after litellm support."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-10T10:00:00Z",
            "eval_proxy_timestamp": "2024-01-15T10:00:00Z",
            "prod_proxy_timestamp": "2024-01-20T10:00:00Z",
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 0

    def test_eval_proxy_before_litellm(self):
        """Test error when eval proxy is before litellm."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-15T10:00:00Z",
            "eval_proxy_timestamp": "2024-01-10T10:00:00Z",  # Before litellm
            "prod_proxy_timestamp": None,
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 1
        assert "eval_proxy_timestamp" in errors[0]
        assert "before litellm_support_timestamp" in errors[0]

    def test_prod_proxy_before_litellm(self):
        """Test error when prod proxy is before litellm."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-15T10:00:00Z",
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": "2024-01-10T10:00:00Z",  # Before litellm
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 1
        assert "prod_proxy_timestamp" in errors[0]

    def test_both_proxies_before_litellm(self):
        """Test errors when both proxies are before litellm."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-15T10:00:00Z",
            "eval_proxy_timestamp": "2024-01-05T10:00:00Z",
            "prod_proxy_timestamp": "2024-01-10T10:00:00Z",
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 2

    def test_no_litellm_support(self):
        """Test when litellm support is not set (no validation possible)."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": None,
            "eval_proxy_timestamp": "2024-01-15T10:00:00Z",
            "prod_proxy_timestamp": "2024-01-20T10:00:00Z",
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 0  # Can't validate without litellm timestamp

    def test_no_proxy_support(self):
        """Test when proxy support is not set."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-15T10:00:00Z",
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
        }
        errors = validate_proxy_after_litellm(model)
        assert len(errors) == 0


class TestValidateData:
    """Tests for validate_data function."""

    def test_validate_valid_data(self):
        """Test validation of valid data file."""
        data = [
            {
                "model_id": "model-1",
                "litellm_support_timestamp": "2024-01-10T10:00:00Z",
                "eval_proxy_timestamp": "2024-01-15T10:00:00Z",
                "prod_proxy_timestamp": "2024-01-20T10:00:00Z",
            },
            {
                "model_id": "model-2",
                "litellm_support_timestamp": "2024-02-01T10:00:00Z",
                "eval_proxy_timestamp": "2024-02-05T10:00:00Z",
                "prod_proxy_timestamp": None,
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_file = Path(f.name)
        
        try:
            errors = validate_data(temp_file)
            assert len(errors) == 0
        finally:
            temp_file.unlink()

    def test_validate_invalid_data(self):
        """Test validation catches invalid data."""
        data = [
            {
                "model_id": "model-1",
                "litellm_support_timestamp": "2024-01-15T10:00:00Z",
                "eval_proxy_timestamp": "2024-01-10T10:00:00Z",  # Invalid
                "prod_proxy_timestamp": "2024-01-20T10:00:00Z",
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_file = Path(f.name)
        
        try:
            errors = validate_data(temp_file)
            assert len(errors) == 1
        finally:
            temp_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
