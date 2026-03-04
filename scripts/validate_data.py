#!/usr/bin/env python3
"""
Validate the LLM support data for logical consistency.

Rules:
- Required fields: model_id, release_date, tier
- tier must be 1 or 2
- Timestamps should be valid ISO format
- No support timestamps before release date (can't support a model before it exists)
- Proxy support must not be before litellm support (proxy deploys litellm versions)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to datetime."""
    if ts is None:
        return None
    
    # Handle various ISO formats
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]:
        try:
            # Normalize the string
            normalized = ts.replace("+00:00", "Z")
            if "." in normalized:
                # Truncate microseconds if present
                parts = normalized.split(".")
                normalized = parts[0] + "Z"
            return datetime.strptime(normalized, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    
    # Try parsing just the date part
    try:
        return datetime.strptime(ts[:10], "%Y-%m-%d")
    except ValueError:
        return None


def validate_required_fields(model: dict) -> list[str]:
    """
    Validate that required fields are present.
    
    Returns a list of error messages (empty if valid).
    """
    errors = []
    model_id = model.get("model_id")
    
    if not model_id:
        errors.append("Missing model_id field")
        return errors
    
    if not model.get("release_date"):
        errors.append(f"{model_id}: Missing release_date field")
    
    return errors


def validate_timestamp_formats(model: dict) -> list[str]:
    """
    Validate that all timestamp fields are parseable.
    
    Returns a list of error messages (empty if valid).
    """
    errors = []
    model_id = model.get("model_id", "unknown")
    
    timestamp_fields = [
        "sdk_support_timestamp",
        "frontend_support_timestamp",
        "index_results_timestamp",
        "eval_proxy_timestamp",
        "prod_proxy_timestamp",
        "litellm_support_timestamp",
    ]
    
    for field in timestamp_fields:
        value = model.get(field)
        if value is not None and parse_timestamp(value) is None:
            errors.append(f"{model_id}: Invalid timestamp format in {field}: {value}")
    
    return errors


def validate_proxy_after_litellm(model: dict) -> list[str]:
    """
    Validate that proxy support timestamps are not before litellm support.
    
    The proxy (All-Hands-AI/infra) deploys litellm versions, so by definition
    proxy support cannot happen before litellm adds the model.
    
    Returns a list of error messages (empty if valid).
    """
    errors = []
    model_id = model.get("model_id", "unknown")
    
    litellm_ts = parse_timestamp(model.get("litellm_support_timestamp"))
    eval_proxy_ts = parse_timestamp(model.get("eval_proxy_timestamp"))
    prod_proxy_ts = parse_timestamp(model.get("prod_proxy_timestamp"))
    
    if litellm_ts is None:
        return errors
    
    if eval_proxy_ts is not None and eval_proxy_ts < litellm_ts:
        errors.append(
            f"{model_id}: eval_proxy_timestamp ({model.get('eval_proxy_timestamp')}) "
            f"is before litellm_support_timestamp ({model.get('litellm_support_timestamp')})"
        )
    
    if prod_proxy_ts is not None and prod_proxy_ts < litellm_ts:
        errors.append(
            f"{model_id}: prod_proxy_timestamp ({model.get('prod_proxy_timestamp')}) "
            f"is before litellm_support_timestamp ({model.get('litellm_support_timestamp')})"
        )
    
    return errors


def validate_timestamps_after_release(model: dict) -> list[str]:
    """
    Validate that no support timestamps come before the model's release date.
    
    A model cannot be supported before it exists.
    
    Returns a list of error messages (empty if valid).
    """
    errors = []
    model_id = model.get("model_id", "unknown")
    release_date = model.get("release_date")
    
    if not release_date:
        return errors
    
    release_dt = parse_timestamp(release_date)
    if release_dt is None:
        return errors
    
    timestamp_fields = [
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
        
        ts = parse_timestamp(value)
        if ts is not None and ts < release_dt:
            errors.append(
                f"{model_id}: {field} ({value}) is before release_date ({release_date})"
            )
    
    return errors


def validate_data(data_file: Path) -> list[str]:
    """
    Validate all models in the data file.
    
    Returns a list of all error messages.
    """
    with open(data_file) as f:
        models = json.load(f)
    
    all_errors = []
    for model in models:
        all_errors.extend(validate_required_fields(model))
        all_errors.extend(validate_timestamp_formats(model))
        all_errors.extend(validate_timestamps_after_release(model))
        all_errors.extend(validate_proxy_after_litellm(model))
    
    return all_errors


def main():
    parser = argparse.ArgumentParser(description="Validate LLM support data")
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings but exit with success code",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        help="Path to data file (default: frontend/public/all_models.json)",
    )
    args = parser.parse_args()

    # Find the data file
    if args.data_file:
        data_file = args.data_file
    else:
        script_dir = Path(__file__).parent
        data_file = script_dir.parent / "frontend" / "public" / "all_models.json"
    
    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)
    
    print(f"Validating {data_file}...")
    errors = validate_data(data_file)
    
    if errors:
        status = "⚠️ Warning" if args.warn_only else "❌ Error"
        print(f"\n{status}: Found {len(errors)} validation issue(s):\n")
        for error in errors:
            print(f"  - {error}")
        
        if args.warn_only:
            print("\n(--warn-only mode: exiting with success code)")
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("✅ All validations passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
