ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry

WORKDIR /app
COPY . .

RUN poetry install --no-root --only main \
    && poetry install --only main

ENTRYPOINT ["python", "-m", "alpha_signal"]
