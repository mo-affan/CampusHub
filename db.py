"""Database helpers for CampusHub (MySQL via mysql-connector-python)."""
import os

from dotenv import load_dotenv
from mysql.connector import pooling

load_dotenv()

pool = pooling.MySQLConnectionPool(
    pool_name="campushub",
    pool_size=5,
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "campushub"),
)


def query(sql, params=None):
    """Run a SELECT and return a list of dict rows."""
    conn = pool.get_connection()
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


def execute(sql, params=()):
    """Run INSERT / UPDATE / DELETE and commit. Returns rows affected."""
    conn = pool.get_connection()
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
    conn = pool.get_connection()
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
