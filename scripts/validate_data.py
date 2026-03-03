#!/usr/bin/env python3
"""
Validate the LLM support data for logical consistency.

Rules:
- Proxy support (eval_proxy_timestamp, prod_proxy_timestamp) must not be before
  litellm_support_timestamp, as the proxy is based on litellm.
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


def validate_proxy_after_litellm(model: dict) -> list[str]:
    """
    Validate that proxy support timestamps are not before litellm support.
    
    Returns a list of error messages (empty if valid).
    """
    errors = []
    model_id = model.get("model_id", "unknown")
    
    litellm_ts = parse_timestamp(model.get("litellm_support_timestamp"))
    eval_proxy_ts = parse_timestamp(model.get("eval_proxy_timestamp"))
    prod_proxy_ts = parse_timestamp(model.get("prod_proxy_timestamp"))
    
    # If litellm support is not set, proxy support should also not be set
    # (or we can't validate the order)
    if litellm_ts is None:
        # This is okay - litellm might not support the model yet
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


def validate_data(data_file: Path) -> list[str]:
    """
    Validate all models in the data file.
    
    Returns a list of all error messages.
    """
    with open(data_file) as f:
        models = json.load(f)
    
    all_errors = []
    for model in models:
        errors = validate_proxy_after_litellm(model)
        all_errors.extend(errors)
    
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
        help="Path to data file (default: data/all_models.json)",
    )
    args = parser.parse_args()

    # Find the data file
    if args.data_file:
        data_file = args.data_file
    else:
        script_dir = Path(__file__).parent
        data_file = script_dir.parent / "data" / "all_models.json"
    
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
