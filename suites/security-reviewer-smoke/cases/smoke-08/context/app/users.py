import sqlite3

MAX_PAGE = 100


def lookup_user(conn: sqlite3.Connection, name: str):
    """Return (id, email) for a user name, or None."""
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE name = ?", (name,))
    return cur.fetchone()


def list_users(conn: sqlite3.Connection, limit: int = 20, offset: int = 0):
    """One page of (id, name), ordered by id."""
    limit = max(1, min(int(limit), MAX_PAGE))
    offset = max(0, int(offset))
    cur = conn.execute("SELECT id, name FROM users ORDER BY id LIMIT ? OFFSET ?", (limit, offset))
    return cur.fetchall()
