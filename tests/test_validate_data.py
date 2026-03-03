"""Tests for the data validation script."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from validate_data import (
    parse_timestamp,
    validate_required_fields,
    validate_timestamp_formats,
    validate_data,
)


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


class TestValidateRequiredFields:
    """Tests for validate_required_fields function."""

    def test_valid_model(self):
        """Test model with all required fields."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
        }
        errors = validate_required_fields(model)
        assert len(errors) == 0

    def test_missing_model_id(self):
        """Test error when model_id is missing."""
        model = {
            "release_date": "2024-01-15",
        }
        errors = validate_required_fields(model)
        assert len(errors) == 1
        assert "model_id" in errors[0]

    def test_missing_release_date(self):
        """Test error when release_date is missing."""
        model = {
            "model_id": "test-model",
        }
        errors = validate_required_fields(model)
        assert len(errors) == 1
        assert "release_date" in errors[0]


class TestValidateTimestampFormats:
    """Tests for validate_timestamp_formats function."""

    def test_valid_timestamps(self):
        """Test model with valid timestamp formats."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "2024-01-15T10:00:00Z",
            "eval_proxy_timestamp": "2024-01-20T10:00:00Z",
        }
        errors = validate_timestamp_formats(model)
        assert len(errors) == 0

    def test_invalid_timestamp(self):
        """Test error for invalid timestamp format."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": "not-a-timestamp",
        }
        errors = validate_timestamp_formats(model)
        assert len(errors) == 1
        assert "Invalid timestamp" in errors[0]

    def test_null_timestamps_ok(self):
        """Test that null timestamps are acceptable."""
        model = {
            "model_id": "test-model",
            "litellm_support_timestamp": None,
            "eval_proxy_timestamp": None,
        }
        errors = validate_timestamp_formats(model)
        assert len(errors) == 0


class TestValidateData:
    """Tests for validate_data function."""

    def test_validate_valid_data(self):
        """Test validation of valid data file."""
        data = [
            {
                "model_id": "model-1",
                "release_date": "2024-01-01",
                "litellm_support_timestamp": "2024-01-10T10:00:00Z",
                "eval_proxy_timestamp": "2024-01-15T10:00:00Z",
                "prod_proxy_timestamp": "2024-01-20T10:00:00Z",
            },
            {
                "model_id": "model-2",
                "release_date": "2024-02-01",
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

    def test_validate_missing_required_fields(self):
        """Test validation catches missing required fields."""
        data = [
            {
                "model_id": "model-1",
                # Missing release_date
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_file = Path(f.name)
        
        try:
            errors = validate_data(temp_file)
            assert len(errors) == 1
            assert "release_date" in errors[0]
        finally:
            temp_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
