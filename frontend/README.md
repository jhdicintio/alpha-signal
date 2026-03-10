# Alpha Signal Platform Frontend

Vite + React SPA for browsing articles and extractions served by the platform backend.

## Setup

```bash
npm install
```

## Run (development)

Start the backend first (from repo root or frontend dir):

```bash
cd ../backend && poetry run flask run
```

Then from this directory:

```bash
npm run dev
```

The dev server runs at http://localhost:5173 and proxies `/api` to the backend at http://127.0.0.1:5001.

## Build

```bash
npm run build
```

Output is in `dist/`. For production, serve these static files via the Flask app or a reverse proxy.
