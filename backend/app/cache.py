"""Cache access for the Flask app."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from alpha_signal.cache.sqlite import SQLiteArticleCache

if TYPE_CHECKING:
    from flask import Flask


@contextmanager
def get_cache(app: Flask):
    """Yield a SQLiteArticleCache connected to the configured DB path."""
    path = app.config["ALPHA_SIGNAL_DB_PATH"]
    with SQLiteArticleCache(path) as cache:
        yield cache
