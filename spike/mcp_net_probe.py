"""Spike 0 probe: does an MCP server launched by Codex (or Claude Code) keep
network access and the ability to run `claude -p`, even when the host CLI's
own command sandbox is read-only?

Install:  pip install "mcp>=1.2"
Register: see spike/README.md
"""

import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sendesis-probe")


@mcp.tool()
def net_probe(url: str = "https://api.anthropic.com") -> str:
    """Resolve DNS and make one HTTPS request. Any HTTP status means the network works."""
    host = url.split("//", 1)[-1].split("/", 1)[0]
    try:
        addrs = socket.getaddrinfo(host, 443)
        dns = f"DNS ok ({addrs[0][4][0]})"
    except OSError as exc:
        return f"FAIL dns: {exc}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return f"{dns}; HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return f"{dns}; HTTP {exc.code} (network OK, server said no)"
    except Exception as exc:  # noqa: BLE001 - spike code, report everything
        return f"{dns}; FAIL http: {type(exc).__name__}: {exc}"


@mcp.tool()
def claude_pong(timeout_s: int = 60) -> str:
    """Run `claude -p` from inside this MCP server process and report the result."""
    binary = shutil.which("claude")
    if not binary:
        return f"FAIL: claude not on PATH ({os.environ.get('PATH', '')})"
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [binary, "-p", "Reply with only the word PONG", "--output-format", "json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return f"FAIL: timed out after {timeout_s}s (likely no network)"
    elapsed = time.monotonic() - started
    tail = (proc.stdout or proc.stderr)[-600:]
    return f"exit={proc.returncode} elapsed={elapsed:.1f}s output_tail={tail}"


@mcp.tool()
def where_am_i() -> str:
    """Report the server's working directory, user and whether $HOME is writable."""
    home = os.path.expanduser("~")
    probe = os.path.join(home, ".sendesis-probe-write-test")
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        home_writable = True
    except OSError:
        home_writable = False
    return f"cwd={os.getcwd()} user={os.environ.get('USER')} home={home} home_writable={home_writable}"


if __name__ == "__main__":
    mcp.run()
