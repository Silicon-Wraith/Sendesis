# Spike 0: MCP sandbox probe

Question: when Codex runs with `--sandbox read-only`, does an MCP server it launches still have network access and the ability to run `claude -p`? If yes, Sendesis can be used from inside Codex through MCP. If no, in-CLI use from Codex needs another route.

## Setup

Use a virtualenv inside this repo so nothing lands in your base environment.

```bash
cd /path/to/sendesis
python3 -m venv .venv
.venv/bin/pip install "mcp>=1.2" jsonschema pyyaml
```

Register the probe with each CLI. Check the exact syntax with `codex mcp --help` and `claude mcp --help` first; these subcommands exist in recent versions but flags change.

```bash
codex mcp add sendesis-probe -- /path/to/sendesis/.venv/bin/python /path/to/sendesis/spike/mcp_net_probe.py
claude mcp add sendesis-probe -- /path/to/sendesis/.venv/bin/python /path/to/sendesis/spike/mcp_net_probe.py
```

If `codex mcp add` is not available, add this to `~/.codex/config.toml` instead:

```toml
[mcp_servers.sendesis-probe]
command = "/path/to/sendesis/.venv/bin/python"
args = ["/path/to/sendesis/spike/mcp_net_probe.py"]
```

## Test from Codex (the one that decides the design)

```bash
cd /path/to/sendesis
codex exec --sandbox read-only \
  "Call the sendesis-probe MCP tools where_am_i, net_probe, and claude_pong in that order. Show each raw result." </dev/null
```

| Result | Meaning |
| --- | --- |
| `net_probe` shows DNS ok and an HTTP status, `claude_pong` shows `exit=0` with PONG | MCP servers run outside the sandbox. In-CLI use from Codex works. |
| `net_probe` fails DNS | Codex sandboxes MCP servers too. Record it; in-CLI use from Codex needs network enabled for the server or a different route. |
| Codex refuses or asks to approve the tool call | Note the message. `codex exec` may need MCP tool approval configured. |

## Test from Claude Code (expected to pass)

```bash
claude -p "Call the sendesis-probe MCP tools where_am_i, net_probe, and claude_pong. Show each raw result." \
  --allowedTools "mcp__sendesis-probe__where_am_i,mcp__sendesis-probe__net_probe,mcp__sendesis-probe__claude_pong" \
  --output-format json
```

## Clean up

When done, remove the probe registration (`codex mcp remove sendesis-probe`, `claude mcp remove sendesis-probe`, or delete the TOML block). Record the results in the plan's Spike 0 section.
