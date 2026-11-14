"""Durable game storage. SQLite and JSON remain available for offline play."""
from contextlib import contextmanager
import os

DATABASE_URL = os.environ.get("GAME_DATABASE_URL")
SCHEMA = "social_wars"
if DATABASE_URL:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb


@contextmanager
def connect():
    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as connection:
        connection.execute(f"SET LOCAL search_path TO {SCHEMA}, pg_catalog")
        yield connection


def load_files():
    with connect() as db:
        rows = db.execute("SELECT path, data FROM game_files").fetchall()
    return {row["path"]: row["data"] for row in rows}


def save_file(path, data):
    with connect() as db:
        db.execute(
            "INSERT INTO game_files (path, data) VALUES (%s, %s) "
            "ON CONFLICT (path) DO UPDATE SET data=EXCLUDED.data",
            (path, Jsonb(data)),
        )
