# Alpha Signal

Turn unstructured scientific articles into actionable trading insights.

Alpha Signal ingests abstracts from multiple scientific article databases, uses LLMs to extract structured data (technologies, sectors, maturity levels, claims), and surfaces signals that could inform trades on emerging technologies.

## Repository layout

There is **no root Poetry project**. Two independent projects:

| Path | Purpose |
|------|---------|
| **`alpha_signal/`** | Standalone Poetry project: the core service (ingestion, extraction, models, workflows, tests). Install with `cd alpha_signal && poetry install` or `task install`. |
| **`backend/`** | Flask API (own Poetry project, path dependency `../alpha_signal`). |
| **`frontend/`** | React SPA (Vite). |

No inheritance: the platform depends on the alpha_signal **project** only as a path dependency; they are sibling projects.

## Architecture

```
Sources (arXiv, OpenAlex, Semantic Scholar, Europe PMC, Springer)
    │
    ▼
┌──────────┐     ┌───────────┐     ┌────────────┐
│  Ingest  │────▶│   Cache   │────▶│  Extract   │
│ (search, │     │ (SQLite)  │◀────│ (any LLM)  │
│  dedup)  │     │           │     │            │
└──────────┘     └───────────┘     └────────────┘
                       │
     articles + extracted fields (technologies, sectors,
     maturity, claims) live in SQLite; can export to extractions.json
```

**Key modules** (inside `alpha_signal/alpha_signal/`):

| Package | Purpose |
|---------|---------|
| `sources/` | OOP wrappers for scientific article APIs |
| `cache/` | SQLite persistence for ingested articles |
| `extractors/` | LLM-powered structured extraction |
| `monitoring/` | Token counting, cost estimation, budget enforcement |
| `services/` | Orchestration functions (ingestion, extraction) |
| `workflows/` | Flyte tasks and workflows for the full pipeline |
| `tests/` | Unit and integration tests |

## Quick Start

### Prerequisites

- Python 3.12
- [Poetry](https://python-poetry.org/docs/#installation)
- [Task](https://taskfile.dev/installation/) (optional, for convenience commands)

### Install

```bash
git clone <your-repo-url>
cd alpha-signal
task install   # installs the alpha_signal service (cd alpha_signal && poetry install)
```

To run the platform: `cd backend && poetry install` and `cd frontend && npm install`.

### Set up environment

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
```

Load it in your shell (or use [direnv](https://direnv.net/)):

```bash
export $(cat .env | xargs)
```

## Usage

### Step 1: Ingest articles (free)

Search scientific sources and cache the results locally:

```bash
task ingest QUERY="solid state batteries"

# Customize sources and result count
task ingest QUERY="quantum computing" SOURCES="arxiv,openalex" MAX_RESULTS=50
```

**Restrict by publication/submission date** (optional):

- **Single day:** set both `DATE_FROM` and `DATE_TO` to the same ISO date.
- **Range:** set `DATE_FROM` and/or `DATE_TO` (YYYY-MM-DD). Sources that support it filter server-side; others may filter client-side.
- **Full year:** e.g. `DATE_FROM=2024-01-01 DATE_TO=2024-12-31`.

```bash
task ingest QUERY="battery" DATE_FROM=2024-01-01 DATE_TO=2024-12-31
task ingest QUERY="quantum" DATE_FROM=2024-06-15 DATE_TO=2024-06-15
```

### Step 2: Estimate extraction cost (free)

See what the LLM extraction will cost before spending anything:

```bash
task estimate
```

### Step 3: Run extraction (costs money)

Extract structured data with a budget cap:

```bash
task extract BUDGET=0.50
```

Results are written to `extractions.json` with this structure:

```json
{
  "article": {
    "title": "...",
    "source": "arxiv",
    "doi": "...",
    "authors": ["..."]
  },
  "extraction": {
    "technologies": [
      {
        "technology": "solid-state lithium-sulfur batteries",
        "sector": "Energy Storage",
        "maturity": "lab_scale",
        "relevance": "Could displace lithium-ion in EVs if scaled."
      }
    ],
    "claims": [{"statement": "400 Wh/kg over 500 cycles", "quantitative": true}],
    "novelty": "novel",
    "sentiment": "optimistic",
    "summary": "New electrolyte approach could make Li-S batteries commercially viable."
  }
}
```

### Full pipeline (one command)

```bash
task pipeline QUERY="CRISPR gene therapy" BUDGET=1.00
```

### Local SLM extraction (CPU, no API key)

You can run extraction with small language models from Hugging Face on local CPU (including fine-tuned adapters). Install the optional dependencies, then pass `--provider local` and the model id or path:

```bash
cd alpha_signal && poetry install --extras local

# Off-the-shelf model (e.g. Qwen 0.5B)
cd alpha_signal && poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --provider local

# Fine-tuned model: use a local path that contains adapter_config.json + weights
cd alpha_signal && poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
  --model /path/to/adapter \
  --provider local
```

Cost is $0. Use `max_concurrency=1` (or low) for CPU. Articles that fail parse/validation are retried once, then skipped unless you configure a fallback.

**Optimizing local extraction**

- **GPU**: Use a CUDA device for much faster inference. Pass `--device cuda` (or `cuda:0`, `cuda:1`, etc.). The model is automatically compiled with `torch.compile` on GPU when available (PyTorch 2+).
- **Parallelism on GPU**: With `--device cuda`, try `--max_concurrency 2` or `4` to overlap tokenization and I/O with generation. On CPU, keep `max_concurrency=1` to avoid thrashing.
- **CPU**: PyTorch uses multiple threads by default for matmul. To cap or tune: set `OMP_NUM_THREADS` or `MKL_NUM_THREADS` before running (e.g. `OMP_NUM_THREADS=8`).

Example with GPU and higher concurrency:

```bash
cd alpha_signal && poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
  --model Qwen/Qwen2.5-0.5B-Instruct --provider local \
  --device cuda --max_concurrency 4
```

### Direct pyflyte usage

From the **alpha_signal** project directory (or use `task ingest`, `task extract`, etc. from repo root):

```bash
cd alpha_signal

poetry run pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
    --query "perovskite solar cells" \
    --sources "arxiv,openalex,europe_pmc" \
    --max_results_per_source 20

# Optional date range (YYYY-MM-DD)
poetry run pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
    --query "battery" --date_from 2024-01-01 --date_to 2024-12-31

poetry run pyflyte run alpha_signal/workflows/extract.py estimate_wf

poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
    --budget_usd 0.50
```

## Development

### Run tests

```bash
task test              # unit tests only (fast, no network)
task test-all          # unit + integration (hits live APIs)
task test-integration  # integration only
```

### Lint and format

```bash
task lint
task fmt
```

### Platform (frontend + backend)

A read-only Flask API and React frontend in `backend/` and `frontend/` let you browse articles and extractions in the browser.

1. Install backend: `cd backend && poetry install`
2. Install frontend: `cd frontend && npm install`
3. From repo root, run both: `task platform` (or run `task platform-backend` and `task platform-frontend` in two terminals)

Backend: http://127.0.0.1:5000. Frontend: http://localhost:5173 (proxies `/api` to the backend). Set `ALPHA_SIGNAL_DB_PATH` if your SQLite DB is not at repo root `articles.db`.

### Available sources

| Source | Auth | Notes |
|---|---|---|
| `arxiv` | None | Pre-prints — fastest signal |
| `openalex` | None | ~250M works, fully open |
| `semantic_scholar` | Optional API key | Rich metadata, fields of study |
| `europe_pmc` | None | Biomedical / pharma focus |
| `springer` | Required API key | Publisher catalog |

### Cost reference (gpt-4o-mini)

| Scale | Est. Input Tokens | Est. Cost |
|---|---|---|
| 100 articles | ~60K | ~$0.03 |
| 1,000 articles | ~600K | ~$0.33 |
| 10,000 articles | ~6M | ~$3.30 |
| 100,000 articles | ~60M | ~$33.00 |
