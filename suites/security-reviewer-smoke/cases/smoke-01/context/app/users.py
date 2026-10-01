import sqlite3


def lookup_user(conn: sqlite3.Connection, name: str):
    """Return (id, email) for a user name, or None."""
    cur = conn.cursor()
    cur.execute(f"SELECT id, email FROM users WHERE name = '{name}'")
    return cur.fetchone()


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
