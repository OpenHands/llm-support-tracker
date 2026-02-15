# OpenHands LLM Support Tracker

This repository tracks when language models are supported across the OpenHands ecosystem:
- [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) - SDK support
- [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) - Frontend dropdown menu
- [OpenHands/openhands-index-results](https://github.com/OpenHands/openhands-index-results) - Index results

## Usage

### Running the Script

```bash
python scripts/track_llm_support.py \
  --model-id "claude-opus-4-5" \
  --release-date "2025-11-01" \
  --output "data/claude-opus-4-5.json"
```

### Arguments

- `--model-id` / `-m`: Language model ID to track (required)
- `--release-date` / `-r`: Release date of the model in ISO format (required)
- `--output` / `-o`: Output JSON file path (required)

### Output Format

The script outputs a JSON file with the following structure:

```json
{
  "model_id": "claude-opus-4-5",
  "release_date": "2025-11-01",
  "sdk_support_timestamp": "2025-11-15T10:30:00Z",
  "frontend_support_timestamp": "2025-11-20T14:00:00Z",
  "index_results_timestamp": "2025-11-25T09:00:00Z"
}
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
