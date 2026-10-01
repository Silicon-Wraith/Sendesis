"""Generate the security-reviewer smoke suite: small planted cases with exact labels."""

import difflib
import shutil
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent.parent / "suites" / "security-reviewer-smoke" / "cases"

CASES = [
    dict(id="smoke-01", clean=False, file="app/users.py", cwe="CWE-89", vuln='cur.execute(f"SELECT id, email FROM users WHERE name = \'{name}\'")',
         notes="lookup_user builds SQL with an f-string from the name argument",
         old='''import sqlite3


def lookup_user(conn: sqlite3.Connection, name: str):
    """Return (id, email) for a user name, or None."""
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE name = ?", (name,))
    return cur.fetchone()


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
''',
         new='''import sqlite3


def lookup_user(conn: sqlite3.Connection, name: str):
    """Return (id, email) for a user name, or None."""
    cur = conn.cursor()
    cur.execute(f"SELECT id, email FROM users WHERE name = '{name}'")
    return cur.fetchone()


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
'''),
    dict(id="smoke-02", clean=False, file="tools/archive.py", cwe="CWE-78", vuln='subprocess.run(f"tar -czf {out_name} {folder}", shell=True',
         notes="archive_folder passes request-supplied names to a shell",
         old='''import subprocess
from pathlib import Path

EXPORT_ROOT = Path("/srv/exports")


def archive_folder(folder: str, out_name: str) -> Path:
    """Called from the export endpoint with folder and out_name from the request."""
    target = EXPORT_ROOT / out_name
    subprocess.run(["tar", "-czf", str(target), "--", folder], check=True)
    return target
''',
         new='''import subprocess
from pathlib import Path

EXPORT_ROOT = Path("/srv/exports")


def archive_folder(folder: str, out_name: str) -> Path:
    """Called from the export endpoint with folder and out_name from the request."""
    target = EXPORT_ROOT / out_name
    subprocess.run(f"tar -czf {out_name} {folder}", shell=True, check=True, cwd=EXPORT_ROOT)
    return target
'''),
    dict(id="smoke-03", clean=False, file="web/files.py", cwe="CWE-22", vuln="return send_file(os.path.join(UPLOAD_DIR, name))",
         notes="download joins a user-supplied name onto the upload dir with no containment check",
         old='''import os

from flask import Flask, abort, request, send_file

app = Flask(__name__)
UPLOAD_DIR = "/srv/uploads"


@app.get("/download")
def download():
    name = request.args.get("name", "")
    path = os.path.realpath(os.path.join(UPLOAD_DIR, name))
    if not path.startswith(UPLOAD_DIR + os.sep):
        abort(404)
    return send_file(path)
''',
         new='''import os

from flask import Flask, abort, request, send_file

app = Flask(__name__)
UPLOAD_DIR = "/srv/uploads"


@app.get("/download")
def download():
    name = request.args.get("name", "")
    if not name:
        abort(404)
    return send_file(os.path.join(UPLOAD_DIR, name))
'''),
    dict(id="smoke-04", clean=False, file="static/comments.js", cwe="CWE-79", vuln="item.innerHTML = `<b>${c.author}</b>: ${c.body}`;",
         notes="renderComments writes user-authored comment text as HTML",
         old='''export function renderComments(list, comments) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    const author = document.createElement("b");
    author.textContent = c.author;
    item.append(author, `: ${c.body}`);
    list.append(item);
  }
}
''',
         new='''export function renderComments(list, comments) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    item.innerHTML = `<b>${c.author}</b>: ${c.body}`;
    list.append(item);
  }
}
'''),
    dict(id="smoke-05", clean=False, file="api/session.py", cwe="CWE-502", vuln="state = pickle.loads(base64.b64decode(raw))",
         notes="restore_session unpickles a client-supplied cookie",
         old='''import base64
import json

from flask import request


def restore_session() -> dict:
    """Read the client's saved UI state from the ui_state cookie."""
    raw = request.cookies.get("ui_state")
    if not raw:
        return {}
    state = json.loads(base64.b64decode(raw))
    return state if isinstance(state, dict) else {}
''',
         new='''import base64
import pickle

from flask import request


def restore_session() -> dict:
    """Read the client's saved UI state from the ui_state cookie."""
    raw = request.cookies.get("ui_state")
    if not raw:
        return {}
    state = pickle.loads(base64.b64decode(raw))
    return state if isinstance(state, dict) else {}
'''),
    dict(id="smoke-06", clean=False, file="web/auth.py", cwe="CWE-601", vuln='return redirect(request.args.get("next", "/"))',
         notes="login redirects to any next URL, including other hosts",
         old='''from urllib.parse import urlparse

from flask import redirect, request

from .session import check_password, start_session


def login_done(user):
    start_session(user)
    target = request.args.get("next", "/")
    if urlparse(target).netloc or not target.startswith("/"):
        target = "/"
    return redirect(target)
''',
         new='''from flask import redirect, request

from .session import check_password, start_session


def login_done(user):
    start_session(user)
    return redirect(request.args.get("next", "/"))
'''),
    dict(id="smoke-07", clean=True, file="app/report.py", notes="extracts a helper and renames a variable; no behavior change",
         old='''def monthly_totals(rows):
    out = {}
    for r in rows:
        k = r["date"][:7]
        out[k] = out.get(k, 0) + r["amount"]
    return dict(sorted(out.items()))
''',
         new='''def _month(date: str) -> str:
    """'2026-09-30' -> '2026-09'."""
    return date[:7]


def monthly_totals(rows):
    totals = {}
    for row in rows:
        month = _month(row["date"])
        totals[month] = totals.get(month, 0) + row["amount"]
    return dict(sorted(totals.items()))
'''),
    dict(id="smoke-08", clean=True, file="app/users.py", notes="adds a paged listing with a parameterized query and clamped limit",
         old='''import sqlite3


def lookup_user(conn: sqlite3.Connection, name: str):
    """Return (id, email) for a user name, or None."""
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE name = ?", (name,))
    return cur.fetchone()
''',
         new='''import sqlite3

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
'''),
    dict(id="smoke-09", clean=True, file="static/comments.js", notes="adds a comment count label using textContent",
         old='''export function renderComments(list, comments) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    const author = document.createElement("b");
    author.textContent = c.author;
    item.append(author, `: ${c.body}`);
    list.append(item);
  }
}
''',
         new='''export function renderComments(list, comments, counter) {
  list.replaceChildren();
  for (const c of comments) {
    const item = document.createElement("li");
    const author = document.createElement("b");
    author.textContent = c.author;
    item.append(author, `: ${c.body}`);
    list.append(item);
  }
  if (counter) {
    counter.textContent = `${comments.length} comment${comments.length === 1 ? "" : "s"}`;
  }
}
'''),
    dict(id="smoke-10", clean=True, file="tools/retry.py", notes="adds jitter and a cap to a retry backoff",
         old='''import time


def with_retries(fn, attempts=3, delay=0.5):
    for i in range(attempts):
        try:
            return fn()
        except ConnectionError:
            if i == attempts - 1:
                raise
            time.sleep(delay * (2 ** i))
''',
         new='''import random
import time

MAX_DELAY = 8.0


def with_retries(fn, attempts=3, delay=0.5):
    for i in range(attempts):
        try:
            return fn()
        except ConnectionError:
            if i == attempts - 1:
                raise
            wait = min(delay * (2 ** i), MAX_DELAY)
            time.sleep(wait * random.uniform(0.5, 1.0))
'''),
]


def git_diff(path: str, old: str, new: str) -> str:
    body = difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}", n=3)
    return f"diff --git a/{path} b/{path}\n" + "".join(body)


shutil.rmtree(OUT, ignore_errors=True)
for c in CASES:
    d = OUT / c["id"]
    (d / "context" / c["file"]).parent.mkdir(parents=True)
    (d / "context" / c["file"]).write_text(c["new"])
    (d / "diff.patch").write_text(git_diff(c["file"], c["old"], c["new"]))
    labels = []
    if not c["clean"]:
        lines = c["new"].splitlines()
        hits = [i + 1 for i, line in enumerate(lines) if c["vuln"] in line]
        assert len(hits) == 1, (c["id"], hits)
        labels = [{"cwe": c["cwe"], "file": c["file"], "line_start": hits[0], "line_end": hits[0]}]
    meta = {"id": c["id"], "source": "clean" if c["clean"] else "planted", "clean": c["clean"], "labels": labels, "notes": c["notes"]}
    (d / "case.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
print("wrote", len(CASES), "cases")
