# Alpha Signal (service)

Standalone Poetry project: ingests scientific articles and extracts structured signals via LLMs. No UI; used as a library, via Flyte workflows, or from the CLI.

The **platform** (Flask API in `backend/`, React frontend in `frontend/`) is separate; the backend depends on this project via a path dependency.

## Install

```bash
cd alpha_signal
poetry install
```

## Test

```bash
poetry run pytest alpha_signal/tests/unit/ -v
poetry run pytest -v  # unit + integration
```

## Usage

Run Flyte workflows from this directory:

```bash
poetry run pyflyte run alpha_signal/workflows/ingest.py ingest_wf --query "battery" ...
poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf ...
```

From the repo root you can use `task ingest`, `task extract`, etc., which run these commands in `alpha_signal/`.
