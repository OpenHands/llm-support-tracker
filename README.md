# OpenHands LLM Support Tracker

This repository tracks when language models are supported across the OpenHands ecosystem:
- [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) - SDK support
- [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) - Frontend dropdown menu
- [OpenHands/openhands-index-results](https://github.com/OpenHands/openhands-index-results) - Index results

## Usage

### Running the Script for All Models

The recommended way to track all models is to use the `run_all_models.py` script, which outputs a single `data/all_models.json` file:

```bash
python scripts/run_all_models.py
```

### Running for a Single Model

To track a single model, use the `track_llm_support.py` script:

```bash
python scripts/track_llm_support.py \
  --model-id "claude-opus-4-5" \
  --release-date "2025-11-01" \
  --output "/tmp/model_result.json"
```

### Arguments

- `--model-id` / `-m`: Language model ID to track (required)
- `--release-date` / `-r`: Release date of the model in ISO format (required)
- `--output` / `-o`: Output JSON file path (required)

### Output Format

The `data/all_models.json` file contains an array of model support data:

```json
[
  {
    "model_id": "claude-opus-4-5",
    "release_date": "2025-11-01",
    "sdk_support_timestamp": "2025-11-15T10:30:00Z",
    "frontend_support_timestamp": "2025-11-20T14:00:00Z",
    "index_results_timestamp": "2025-11-25T09:00:00Z",
    "eval_proxy_timestamp": "2025-11-12T08:00:00Z",
    "prod_proxy_timestamp": "2025-11-18T12:00:00Z",
    "litellm_support_timestamp": "2025-11-10T16:30:00Z"
  }
]
```

## Frontend

The frontend visualizes the LLM support data. To run it:

```bash
cd frontend
npm install
npm run dev
```

## GitHub Workflow

The repository includes a GitHub workflow that can be triggered to run the script:

```bash
gh workflow run track-llm-support.yml \
  -f model_id="claude-opus-4-5" \
  -f release_date="2025-11-01"
```

## Development

### Requirements

- Python 3.10+
- Node.js 18+ (for frontend)

### Setup

```bash
pip install -r requirements.txt
```

### Running Tests

```bash
pytest tests/
```
