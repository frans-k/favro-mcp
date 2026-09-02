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
- A card can live on several boards at once. The instances share one
  `cardCommonId`; each has its own `cardId`, column and position. `PUT /cards`
  with `dragMode: "commit"` (the API's default) adds an instance on the target
  board, `"move"` relocates the card — see `add_card_to_board`. `get_cards`
  defaults to `unique=True`, which collapses the instances to one arbitrary
  entry; pass `unique=False` to see them separately. `CardResolver`'s sequential
  id lookup takes that default, so `#123` for a multi-board card resolves to an
  arbitrary instance — a card id names one outright
- `CardResolver` reads `prefix-123` as sequential id `#123`, so an identifier
  like `card-1` resolves as `#1` rather than as a card id — worth knowing when
  writing fixtures. `CardResolver.parse_sequential_id` is public so callers can
  ask which path `resolve` will take; comparing the identifier to the resolved
  `cardId` does not answer it
