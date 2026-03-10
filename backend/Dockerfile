# Build from repo root: docker build -f backend/Dockerfile .
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry

WORKDIR /app

# Path dependency: backend depends on alpha_signal
COPY alpha_signal/ /app/alpha_signal/
COPY backend/ /app/backend/

WORKDIR /app/backend
RUN poetry install --no-root --only main \
    && poetry install --only main

ENV FLASK_APP=app:create_app
EXPOSE 5000
CMD ["poetry", "run", "flask", "run", "--host=0.0.0.0"]
