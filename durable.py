"""Durable game storage. SQLite and JSON remain available for offline play."""
from atexit import register
from contextlib import contextmanager
import os

DATABASE_URL = os.environ.get("GAME_DATABASE_URL")
SCHEMA = "social_wars"
if DATABASE_URL:
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    pool = ConnectionPool(
        DATABASE_URL,
        kwargs={"connect_timeout": 8, "row_factory": dict_row, "prepare_threshold": None},
        min_size=1,
        max_size=6,
        max_waiting=30,
        max_idle=60,
        timeout=8,
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open()
    register(pool.close)


@contextmanager
def connect():
    with pool.connection() as connection:
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
