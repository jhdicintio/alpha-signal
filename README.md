# Alpha Signal

Turn unstructured scientific articles into actionable trading insights.

Alpha Signal ingests abstracts from multiple scientific article databases, uses LLMs to extract structured data (technologies, sectors, maturity levels, claims), and surfaces signals that could inform trades on emerging technologies.

## Architecture

```
Sources (arXiv, OpenAlex, Semantic Scholar, Europe PMC, Springer)
    │
    ▼
┌──────────┐     ┌───────────┐     ┌────────────┐
│  Ingest  │────▶│   Cache   │────▶│  Extract   │
│ (search, │     │ (SQLite)  │     │ (OpenAI    │
│  dedup)  │     │           │     │  LLM)      │
└──────────┘     └───────────┘     └────────────┘
                                         │
                                         ▼
                                   extractions.json
                                   (technologies, sectors,
                                    maturity, claims)
```

**Key modules:**

| Package | Purpose |
|---|---|
| `sources/` | OOP wrappers for scientific article APIs |
| `cache/` | SQLite persistence for ingested articles |
| `extractors/` | LLM-powered structured extraction |
| `monitoring/` | Token counting, cost estimation, budget enforcement |
| `services/` | Orchestration functions (ingestion, extraction) |
| `workflows/` | Flyte tasks and workflows for the full pipeline |

## Quick Start

### Prerequisites

- Python 3.12
- [Poetry](https://python-poetry.org/docs/#installation)
- [Task](https://taskfile.dev/installation/) (optional, for convenience commands)

### Install

```bash
git clone <your-repo-url>
cd alpha-signal
poetry install
```

### Set up environment

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=sk-your-key-here
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
poetry install --extras local

# Off-the-shelf model (e.g. Qwen 0.5B)
poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --provider local

# Fine-tuned model: use a local path that contains adapter_config.json + weights
poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
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
poetry run pyflyte run alpha_signal/workflows/extract.py extract_wf \
  --model Qwen/Qwen2.5-0.5B-Instruct --provider local \
  --device cuda --max_concurrency 4
```

### Direct pyflyte usage

All workflows can also be run directly with pyflyte:

```bash
poetry run pyflyte run src/alpha_signal/workflows/ingest.py ingest_wf \
    --query "perovskite solar cells" \
    --sources "arxiv,openalex,europe_pmc" \
    --max_results_per_source 20

# Optional date range (YYYY-MM-DD)
poetry run pyflyte run src/alpha_signal/workflows/ingest.py ingest_wf \
    --query "battery" --date_from 2024-01-01 --date_to 2024-12-31

poetry run pyflyte run src/alpha_signal/workflows/extract.py estimate_wf

poetry run pyflyte run src/alpha_signal/workflows/extract.py extract_wf \
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
