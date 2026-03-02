"""Tests for the data validation script."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from validate_data import (
    REQUIRED_FIELDS,
    parse_timestamp,
    validate_cross_file_consistency,
    validate_data_completeness,
    validate_no_duplicates,
    validate_schema,
    validate_timestamp_format,
    validate_timestamp_ordering,
)


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_iso_format_with_z(self):
        """Test parsing ISO format with Z suffix."""
        result = parse_timestamp("2024-01-15T10:00:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_iso_format_with_timezone(self):
        """Test parsing ISO format with timezone offset."""
        result = parse_timestamp("2024-01-15T10:00:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_iso_format_with_milliseconds(self):
        """Test parsing ISO format with milliseconds."""
        result = parse_timestamp("2024-01-15T10:00:00.000Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_only(self):
        """Test parsing date-only format."""
        result = parse_timestamp("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_null(self):
        """Test parsing None value."""
        result = parse_timestamp(None)
        assert result is None

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        result = parse_timestamp("not-a-date")
        assert result is None

    def test_parse_timezone_with_offset(self):
        """Test parsing timezone with non-zero offset."""
        result = parse_timestamp("2024-01-15T10:00:00.000-08:00")
        assert result is not None


class TestValidateSchema:
    """Tests for validate_schema function."""

    def test_valid_schema(self):
        """Test model with all required fields."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": None,
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_schema(model, "test")
        assert len(errors) == 0

    def test_missing_required_field(self):
        """Test model missing a required field."""
        model = {
            "model_id": "test-model",
            # Missing release_date
            "sdk_support_timestamp": None,
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_schema(model, "test")
        assert len(errors) == 1
        assert "release_date" in errors[0]

    def test_multiple_missing_fields(self):
        """Test model missing multiple fields."""
        model = {"model_id": "test-model"}
        errors, warnings = validate_schema(model, "test")
        assert len(errors) == len(REQUIRED_FIELDS) - 1  # model_id is present


class TestValidateTimestampFormat:
    """Tests for validate_timestamp_format function."""

    def test_valid_timestamps(self):
        """Test model with valid timestamp formats."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-01-20T10:00:00Z",
            "frontend_support_timestamp": "2024-01-25T10:00:00.000Z",
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_format(model, "test")
        assert len(errors) == 0

    def test_invalid_timestamp(self):
        """Test model with invalid timestamp format."""
        model = {
            "model_id": "test-model",
            "release_date": "invalid-date",
            "sdk_support_timestamp": None,
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_format(model, "test")
        assert len(errors) == 1
        assert "Invalid timestamp format" in errors[0]

    def test_placeholder_timestamp_warning(self):
        """Test model with placeholder timestamp generates warning."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-01-15T00:00:00Z",
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_format(model, "test")
        assert len(errors) == 0
        assert len(warnings) == 1
        assert "placeholder" in warnings[0].lower()


class TestValidateTimestampOrdering:
    """Tests for validate_timestamp_ordering function."""

    def test_valid_ordering(self):
        """Test model with valid timestamp ordering."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-01-20T10:00:00Z",
            "frontend_support_timestamp": "2024-01-25T10:00:00Z",
            "index_results_timestamp": "2024-02-01T10:00:00Z",
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_ordering(model, "test")
        assert len(errors) == 0

    def test_support_before_release(self):
        """Test error when support timestamp is before release."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-01-10T10:00:00Z",  # Before release
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_ordering(model, "test")
        assert len(errors) == 1
        assert "before release_date" in errors[0]

    def test_frontend_before_sdk(self):
        """Test error when frontend support is before SDK support."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-01-25T10:00:00Z",
            "frontend_support_timestamp": "2024-01-20T10:00:00Z",  # Before SDK
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_ordering(model, "test")
        assert len(errors) == 1
        assert "frontend_support_timestamp" in errors[0]
        assert "before sdk_support_timestamp" in errors[0]

    def test_index_before_sdk(self):
        """Test error when index results is before SDK support."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": "2024-02-01T10:00:00Z",
            "frontend_support_timestamp": None,
            "index_results_timestamp": "2024-01-20T10:00:00Z",  # Before SDK
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_ordering(model, "test")
        assert len(errors) == 1
        assert "index_results_timestamp" in errors[0]
        assert "before sdk_support_timestamp" in errors[0]

    def test_null_timestamps_no_errors(self):
        """Test that null timestamps don't cause ordering errors."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": None,
            "frontend_support_timestamp": None,
            "index_results_timestamp": None,
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_timestamp_ordering(model, "test")
        assert len(errors) == 0


class TestValidateDataCompleteness:
    """Tests for validate_data_completeness function."""

    def test_index_without_sdk_warning(self):
        """Test warning when index_results is set but sdk is null."""
        model = {
            "model_id": "test-model",
            "release_date": "2024-01-15",
            "sdk_support_timestamp": None,
            "frontend_support_timestamp": None,
            "index_results_timestamp": "2024-02-01T10:00:00Z",
            "eval_proxy_timestamp": None,
            "prod_proxy_timestamp": None,
            "litellm_support_timestamp": None,
        }
        errors, warnings = validate_data_completeness(model, "test")
        assert len(errors) == 0
        assert len(warnings) >= 1
        assert any("sdk_support_timestamp is null" in w for w in warnings)


class TestValidateNoDuplicates:
    """Tests for validate_no_duplicates function."""

    def test_no_duplicates(self):
        """Test list with no duplicate model_ids."""
        models = [
            {"model_id": "model-1"},
            {"model_id": "model-2"},
            {"model_id": "model-3"},
        ]
        errors, warnings = validate_no_duplicates(models, "test")
        assert len(errors) == 0

    def test_with_duplicates(self):
        """Test list with duplicate model_ids."""
        models = [
            {"model_id": "model-1"},
            {"model_id": "model-2"},
            {"model_id": "model-1"},  # Duplicate
        ]
        errors, warnings = validate_no_duplicates(models, "test")
        assert len(errors) == 1
        assert "Duplicate model_id" in errors[0]
        assert "model-1" in errors[0]


class TestValidateCrossFileConsistency:
    """Tests for validate_cross_file_consistency function."""

    def test_consistent_files(self):
        """Test when individual files match all_models.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Create all_models.json
            all_models = [
                {
                    "model_id": "test-model",
                    "release_date": "2024-01-15",
                    "sdk_support_timestamp": None,
                    "frontend_support_timestamp": None,
                    "index_results_timestamp": None,
                    "eval_proxy_timestamp": None,
                    "prod_proxy_timestamp": None,
                    "litellm_support_timestamp": None,
                }
            ]
            with open(data_dir / "all_models.json", "w") as f:
                json.dump(all_models, f)
            
            # Create matching individual file
            with open(data_dir / "test-model.json", "w") as f:
                json.dump(all_models[0], f)
            
            errors, warnings = validate_cross_file_consistency(data_dir, all_models)
            assert len(errors) == 0

    def test_missing_individual_file(self):
        """Test error when individual file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            all_models = [
                {
                    "model_id": "test-model",
                    "release_date": "2024-01-15",
                    "sdk_support_timestamp": None,
                    "frontend_support_timestamp": None,
                    "index_results_timestamp": None,
                    "eval_proxy_timestamp": None,
                    "prod_proxy_timestamp": None,
                    "litellm_support_timestamp": None,
                }
            ]
            with open(data_dir / "all_models.json", "w") as f:
                json.dump(all_models, f)
            
            # Don't create the individual file
            errors, warnings = validate_cross_file_consistency(data_dir, all_models)
            assert len(errors) == 1
            assert "test-model.json" in errors[0]
            assert "missing" in errors[0].lower()

    def test_mismatched_data(self):
        """Test error when individual file doesn't match all_models.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            all_models = [
                {
                    "model_id": "test-model",
                    "release_date": "2024-01-15",
                    "sdk_support_timestamp": "2024-01-20T10:00:00Z",
                    "frontend_support_timestamp": None,
                    "index_results_timestamp": None,
                    "eval_proxy_timestamp": None,
                    "prod_proxy_timestamp": None,
                    "litellm_support_timestamp": None,
                }
            ]
            with open(data_dir / "all_models.json", "w") as f:
                json.dump(all_models, f)
            
            # Create individual file with different data
            individual = all_models[0].copy()
            individual["sdk_support_timestamp"] = "2024-01-25T10:00:00Z"  # Different
            with open(data_dir / "test-model.json", "w") as f:
                json.dump(individual, f)
            
            errors, warnings = validate_cross_file_consistency(data_dir, all_models)
            assert len(errors) == 1
            assert "mismatch" in errors[0].lower()

    def test_orphaned_individual_file(self):
        """Test error when individual file has no entry in all_models.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            all_models = []
            with open(data_dir / "all_models.json", "w") as f:
                json.dump(all_models, f)
            
            # Create orphaned individual file
            orphan = {
                "model_id": "orphan-model",
                "release_date": "2024-01-15",
                "sdk_support_timestamp": None,
                "frontend_support_timestamp": None,
                "index_results_timestamp": None,
                "eval_proxy_timestamp": None,
                "prod_proxy_timestamp": None,
                "litellm_support_timestamp": None,
            }
            with open(data_dir / "orphan-model.json", "w") as f:
                json.dump(orphan, f)
            
            errors, warnings = validate_cross_file_consistency(data_dir, all_models)
            assert len(errors) == 1
            assert "not found in all_models.json" in errors[0]


class TestIntegration:
    """Integration tests for the validation script."""

    def test_validation_on_sample_data(self):
        """Test validation on the actual data directory structure."""
        # Get the actual data directory
        script_dir = Path(__file__).parent
        data_dir = script_dir.parent / "data"
        
        if not data_dir.exists():
            pytest.skip("Data directory not found")
        
        all_models_path = data_dir / "all_models.json"
        if not all_models_path.exists():
            pytest.skip("all_models.json not found")
        
        with open(all_models_path) as f:
            all_models = json.load(f)
        
        # Run schema validation on all models
        for model in all_models:
            errors, warnings = validate_schema(model, "test")
            # Should have no missing fields in actual data
            assert len(errors) == 0, f"Schema errors in {model.get('model_id')}: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
