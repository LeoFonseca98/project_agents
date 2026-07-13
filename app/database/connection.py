from contextlib import contextmanager
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def get_history_connection():
    return psycopg2.connect(
        host=os.getenv("HISTORY_DB_HOST"),
        port=os.getenv("HISTORY_DB_PORT", "5432"),
        dbname=os.getenv("HISTORY_DB_NAME"),
        user=os.getenv("HISTORY_DB_USER"),
        password=os.getenv("HISTORY_DB_PASSWORD"),
    )


@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_history_db():
    conn = get_history_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()