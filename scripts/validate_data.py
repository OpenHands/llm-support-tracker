#!/usr/bin/env python3
"""
Script to validate data coherence in the LLM support tracker.

This script validates:
1. Schema validation - required fields and no duplicates
2. Timestamp ordering - logical ordering of timestamps
3. Timestamp format - valid ISO 8601 format
4. Data completeness - warnings for suspicious patterns
5. Cross-file consistency - individual JSONs match all_models.json
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REQUIRED_FIELDS = [
    "model_id",
    "release_date",
    "sdk_support_timestamp",
    "frontend_support_timestamp",
    "index_results_timestamp",
    "eval_proxy_timestamp",
    "prod_proxy_timestamp",
    "litellm_support_timestamp",
]


def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string to datetime object."""
    if ts is None:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(ts.replace("+00:00", "Z"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # Try parsing with fromisoformat as fallback
    try:
        ts_clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_clean)
        return dt
    except ValueError:
        return None


def validate_schema(model: dict, source: str) -> tuple[list[str], list[str]]:
    """Validate that model has all required fields.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    for field in REQUIRED_FIELDS:
        if field not in model:
            errors.append(f"[{source}] Missing required field: {field}")
    
    return errors, warnings


def validate_timestamp_format(model: dict, source: str) -> tuple[list[str], list[str]]:
    """Validate timestamp format is valid ISO 8601.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    model_id = model.get("model_id", "unknown")
    
    timestamp_fields = [
        "release_date",
        "sdk_support_timestamp",
        "frontend_support_timestamp",
        "index_results_timestamp",
        "eval_proxy_timestamp",
        "prod_proxy_timestamp",
        "litellm_support_timestamp",
    ]
    
    for field in timestamp_fields:
        value = model.get(field)
        if value is None:
            continue
            
        parsed = parse_timestamp(value)
        if parsed is None:
            errors.append(
                f"[{source}] {model_id}: Invalid timestamp format for {field}: {value}"
            )
        elif "T00:00:00Z" in value or "T00:00:00.000" in value:
            warnings.append(
                f"[{source}] {model_id}: Possible placeholder timestamp for {field}: {value}"
            )
    
    return errors, warnings


def validate_timestamp_ordering(model: dict, source: str) -> tuple[list[str], list[str]]:
    """Validate that timestamps are in logical order.
    
    Rules:
    - release_date should be before or equal to all support timestamps
    - sdk_support_timestamp should be before or equal to frontend_support_timestamp
    - sdk_support_timestamp should be before or equal to index_results_timestamp
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    model_id = model.get("model_id", "unknown")
    
    release = parse_timestamp(model.get("release_date"))
    sdk = parse_timestamp(model.get("sdk_support_timestamp"))
    frontend = parse_timestamp(model.get("frontend_support_timestamp"))
    index = parse_timestamp(model.get("index_results_timestamp"))
    
    if release is None:
        return errors, warnings  # Can't validate without release date
    
    # Check that support timestamps are not before release
    support_fields = [
        ("sdk_support_timestamp", sdk),
        ("frontend_support_timestamp", frontend),
        ("index_results_timestamp", index),
        ("eval_proxy_timestamp", parse_timestamp(model.get("eval_proxy_timestamp"))),
        ("prod_proxy_timestamp", parse_timestamp(model.get("prod_proxy_timestamp"))),
        ("litellm_support_timestamp", parse_timestamp(model.get("litellm_support_timestamp"))),
    ]
    
    for field_name, timestamp in support_fields:
        if timestamp is not None and timestamp < release:
            errors.append(
                f"[{source}] {model_id}: {field_name} ({timestamp.isoformat()}) "
                f"is before release_date ({release.isoformat()})"
            )
    
    # Check frontend depends on SDK
    if sdk is not None and frontend is not None:
        if frontend < sdk:
            errors.append(
                f"[{source}] {model_id}: frontend_support_timestamp ({frontend.isoformat()}) "
                f"is before sdk_support_timestamp ({sdk.isoformat()}) - frontend depends on SDK"
            )
    
    # Check index_results requires SDK (can't evaluate without SDK support)
    if sdk is not None and index is not None:
        if index < sdk:
            errors.append(
                f"[{source}] {model_id}: index_results_timestamp ({index.isoformat()}) "
                f"is before sdk_support_timestamp ({sdk.isoformat()}) - can't evaluate without SDK"
            )
    
    return errors, warnings


def validate_data_completeness(model: dict, source: str) -> tuple[list[str], list[str]]:
    """Check for suspicious data patterns.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    model_id = model.get("model_id", "unknown")
    
    sdk = model.get("sdk_support_timestamp")
    index = model.get("index_results_timestamp")
    release = parse_timestamp(model.get("release_date"))
    
    # Warn if index_results_timestamp is set but sdk_support_timestamp is null
    if sdk is None and index is not None:
        warnings.append(
            f"[{source}] {model_id}: sdk_support_timestamp is null but "
            f"index_results_timestamp is set - unusual pattern"
        )
    
    # Warn if model released > 30 days ago but has null support timestamps
    if release is not None:
        now = datetime.now(timezone.utc)
        days_since_release = (now - release).days
        
        if days_since_release > 30:
            null_support_fields = []
            if model.get("sdk_support_timestamp") is None:
                null_support_fields.append("sdk_support_timestamp")
            if model.get("frontend_support_timestamp") is None:
                null_support_fields.append("frontend_support_timestamp")
            
            if null_support_fields:
                warnings.append(
                    f"[{source}] {model_id}: Released {days_since_release} days ago "
                    f"but missing: {', '.join(null_support_fields)}"
                )
    
    return errors, warnings


def validate_no_duplicates(models: list[dict], source: str) -> tuple[list[str], list[str]]:
    """Check for duplicate model_ids in all_models.json.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    seen_ids = {}
    for i, model in enumerate(models):
        model_id = model.get("model_id")
        if model_id in seen_ids:
            errors.append(
                f"[{source}] Duplicate model_id '{model_id}' "
                f"at indices {seen_ids[model_id]} and {i}"
            )
        else:
            seen_ids[model_id] = i
    
    return errors, warnings


def validate_cross_file_consistency(
    data_dir: Path, all_models: list[dict]
) -> tuple[list[str], list[str]]:
    """Validate that individual JSON files match all_models.json entries.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    # Build a mapping of model_id -> data from all_models.json
    all_models_map = {m["model_id"]: m for m in all_models if "model_id" in m}
    
    # Get all individual model JSON files
    individual_files = set()
    for json_file in data_dir.glob("*.json"):
        if json_file.name == "all_models.json":
            continue
        individual_files.add(json_file)
    
    # Check each individual file is in all_models.json and matches
    for json_file in sorted(individual_files):
        try:
            with open(json_file) as f:
                model_data = json.load(f)
            
            model_id = model_data.get("model_id")
            if model_id is None:
                errors.append(
                    f"[{json_file.name}] Missing model_id field"
                )
                continue
            
            # Check if model exists in all_models.json
            if model_id not in all_models_map:
                errors.append(
                    f"[{json_file.name}] Model '{model_id}' not found in all_models.json"
                )
                continue
            
            # Check that data matches
            all_models_entry = all_models_map[model_id]
            for field in REQUIRED_FIELDS:
                individual_value = model_data.get(field)
                all_models_value = all_models_entry.get(field)
                
                if individual_value != all_models_value:
                    errors.append(
                        f"[{json_file.name}] Field '{field}' mismatch: "
                        f"individual={individual_value}, all_models={all_models_value}"
                    )
        
        except json.JSONDecodeError as e:
            errors.append(f"[{json_file.name}] Invalid JSON: {e}")
        except Exception as e:
            errors.append(f"[{json_file.name}] Error reading file: {e}")
    
    # Check for entries in all_models.json without corresponding individual file
    expected_individual_files = {f"{m['model_id']}.json" for m in all_models if "model_id" in m}
    actual_individual_files = {f.name for f in individual_files}
    
    for expected in sorted(expected_individual_files):
        if expected not in actual_individual_files:
            errors.append(
                f"[all_models.json] Model file '{expected}' is missing"
            )
    
    return errors, warnings


def main() -> int:
    """Main entry point for data validation.
    
    Returns:
        0 if validation passes, 1 if errors found
    """
    # Determine data directory
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        return 1
    
    all_models_path = data_dir / "all_models.json"
    if not all_models_path.exists():
        print(f"Error: all_models.json not found: {all_models_path}")
        return 1
    
    all_errors = []
    all_warnings = []
    
    # Load all_models.json
    try:
        with open(all_models_path) as f:
            all_models = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in all_models.json: {e}")
        return 1
    
    if not isinstance(all_models, list):
        print("Error: all_models.json must be a JSON array")
        return 1
    
    print(f"Validating {len(all_models)} models in all_models.json...")
    print()
    
    # Validate no duplicates in all_models.json
    errs, warns = validate_no_duplicates(all_models, "all_models.json")
    all_errors.extend(errs)
    all_warnings.extend(warns)
    
    # Validate each model in all_models.json
    for model in all_models:
        source = f"all_models.json:{model.get('model_id', 'unknown')}"
        
        errs, warns = validate_schema(model, source)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        
        errs, warns = validate_timestamp_format(model, source)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        
        errs, warns = validate_timestamp_ordering(model, source)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        
        errs, warns = validate_data_completeness(model, source)
        all_errors.extend(errs)
        all_warnings.extend(warns)
    
    # Validate cross-file consistency
    errs, warns = validate_cross_file_consistency(data_dir, all_models)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    
    # Print results
    if all_warnings:
        print("=" * 60)
        print("WARNINGS:")
        print("=" * 60)
        for warning in all_warnings:
            print(f"  ⚠️  {warning}")
        print()
    
    if all_errors:
        print("=" * 60)
        print("ERRORS:")
        print("=" * 60)
        for error in all_errors:
            print(f"  ❌ {error}")
        print()
        print(f"Validation failed with {len(all_errors)} error(s)")
        return 1
    
    print("=" * 60)
    print("✅ All validations passed!")
    print("=" * 60)
    if all_warnings:
        print(f"   ({len(all_warnings)} warning(s) noted)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
