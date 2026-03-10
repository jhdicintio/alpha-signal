# Alpha Signal Platform Backend

Flask read-only API for articles and extractions produced by the Alpha Signal pipeline.

## Setup

From this directory:

```bash
poetry install
```

Requires the root `alpha-signal` package (installed as a path dependency).

## Configuration

- `ALPHA_SIGNAL_DB_PATH` – Path to the SQLite database (default: `../../articles.db`, i.e. repo root).
- `FLASK_APP` – Set to `app:create_app()` for `flask run`.

## Run

```bash
export ALPHA_SIGNAL_DB_PATH=../../articles.db  # or your path
poetry run flask run
```

By default the server listens on http://127.0.0.1:5000.

## API

- `GET /api/health` – Health check.
- `GET /api/stats` – Article and extraction counts.
- `GET /api/extractions` – List extractions (pagination: `limit`, `offset`; filters: `source`, `extraction_model`, `sector`).
- `GET /api/extractions/<source>/<source_id>` – Single extraction with article.
- `GET /api/articles` – List articles (pagination: `limit`, `offset`; filters: `source`, `publication_date_from`, `publication_date_to`).
- `GET /api/articles/<source>/<source_id>` – Single article (optional `?with_extraction=1`).
