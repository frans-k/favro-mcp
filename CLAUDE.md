# favro-mcp

Local fork of the [favro-mcp](https://github.com/truls27a/favro-mcp) MCP server,
which exposes Favro project management as MCP tools (boards, columns, cards,
comments, custom fields, tasklists). Favro is our issue tracker — this server
is what lets agents read and update cards.

## Stack

- Python 3.12+
- FastMCP (`fastmcp>=2.0`)
- httpx, pydantic
- uv for dependency management

## Running from source

The workspace is configured to run this local checkout (not the published
`favro-mcp` package on PyPI), so changes here take effect after restart.

```bash
uv sync --dev
uv run python -m favro_mcp
```

Auth is via `FAVRO_EMAIL` and `FAVRO_API_TOKEN` env vars.

## Layout

```text
src/favro_mcp/
  api/          ← thin Favro REST client
  resolvers/    ← name → ID resolution (board names, user names, etc.)
  tools/        ← MCP tool implementations
  server.py     ← FastMCP server setup
  context.py    ← per-request context (current org/board)
```

## Conventions

- This is a fork — keep changes minimal and upstreamable when possible
- Strict pyright is enabled (`typeCheckingMode = "strict"`); keep new code typed
- Favro escapes backticks, brackets, and tildes in card descriptions — tools
  that write descriptions should send plain text, not markdown code formatting
- Markdown checkboxes can't be created via the description API — use the
  tasklist API instead
- Tasklists must be created with a name to get a bold heading in the UI;
  renaming an unnamed list later does not add the heading retroactively
