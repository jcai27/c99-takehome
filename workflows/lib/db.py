"""A single place to open a connection to the chp99 application database.

Mirrors lib/paths.py's DATA_DIR pattern: read from the environment (already
wired into the worker container by docker-compose.yaml), fall back to the
same default the app scaffold uses for a host-run worker.
"""

import os

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgres://postgres:postgres@localhost:5432/chp99"
)


def connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
