FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.0

ARG PYTHON_VERSION=3.12

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-venv \
        python3-pip \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY . .
RUN poetry install --only main

ENTRYPOINT ["python", "-m", "alpha_signal"]
