"""Database helpers for CampusHub (MySQL via mysql-connector-python).

Every function borrows a pooled connection, runs ONE parameterized statement
(or one stored-procedure call) and gives the connection back. User values are
always passed separately from the SQL text, so they can never change the query.
"""
import os
import time

from dotenv import load_dotenv
from mysql.connector import Error, pooling  # noqa: F401  (Error is re-exported for app.py)

load_dotenv()

CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "campushub"),
}
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

_pool = None


def get_pool():
    """Create the pool on first use, so the app can start (and show a clear
    error page) even when MySQL is not running yet."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(pool_name="campushub", pool_size=POOL_SIZE, **CONFIG)
    return _pool


def query(sql, params=None):
    """Run a SELECT and return a list of dict rows."""
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)          # parameterized: no SQL injection
        rows = cur.fetchall()
        conn.commit()                     # end the read transaction (fresh data next time)
        return rows
    finally:
        conn.close()                      # returns the connection to the pool


def one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql, params=None):
    row = one(sql, params)
    return next(iter(row.values())) if row else None


def execute(sql, params=()):
    """Run INSERT / UPDATE / DELETE and commit. Returns rows affected."""
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def call(proc, args):
    """Call a stored procedure; returns the args tuple with OUT values filled in."""
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor()
        result = cur.callproc(proc, args)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping():
    """Round-trip check used by the status page. Returns server info and latency."""
    start = time.perf_counter()
    row = one("SELECT VERSION() AS version, DATABASE() AS db_name, CURRENT_USER() AS db_user")
    return {**row, "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "host": CONFIG["host"], "port": CONFIG["port"], "pool_size": POOL_SIZE}
