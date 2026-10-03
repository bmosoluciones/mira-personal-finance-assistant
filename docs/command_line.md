# Command Line and MCP Server

MIRA ships two entry points: `mira` opens the desktop interface and `mira-cli`
works on a database file without any GUI. The `mira-cli mcp` command speaks
[MCP](https://modelcontextprotocol.io) over stdio so an assistant can call the
same commands.

Everything on this page is local: the CLI never needs Qt, and the MCP server
never needs an LLM.

## Command line

### Flags

| Flag | Entry point | Effect |
| --- | --- | --- |
| `--db PATH` | `mira-cli` | SQLite database file to use. Defaults to the per-user data directory. |
| `--json` | `mira-cli` | Print machine-readable JSON instead of text. |
| `--version` | `mira-cli` | Print the installed package version. |
| `--check` | `mira-cli` | Run a headless dependency check. Does not import Qt. |
| `--debug` | `mira` | Verbose logging in the desktop interface. |

`--check` is the quickest way to confirm an installation works:

```bash
mira-cli --check
```

### Subcommands

| Subcommand | What it does |
| --- | --- |
| `backup` | Copy the database to `--output-file PATH`. |
| `restore` | Replace the database with `--input-file PATH`. |
| `seed` | Populate the current-year database with demo budget and transactions. |
| `income add` | Record income. |
| `expense add` | Record an expense. |
| `transfer` | Transfer money between accounts. |
| `transactions list` | List transactions. |
| `report` | Print a local summary. |
| `record` | Record a transaction with the local parser. |

Examples:

```bash
mira-cli --db ~/finanzas.db backup --output-file ~/finanzas-2026.db
mira-cli expense add --account "Cash" --amount 12.50 --category "Groceries"
mira-cli transfer --from "Cash" --to "Bank" --amount 100
mira-cli --json transactions list --limit 10 --since 2026-05-01
mira-cli report --since 2026-01-01
mira-cli record "gasté 30 euros en el supermercado el 3 de mayo"
```

`record` uses `TransactionParserEngine`, the same structured prompt parser the
desktop interface uses. It does not contact any provider, and it is not chat
mode.

Amounts accept a decimal separator, and `--date` uses `YYYY-MM-DD`. Account
names are resolved as typed; a name that does not exist is reported as an error
instead of creating an account.

## MCP server

### Enabling it

The server is off until you accept it in the desktop interface, because an MCP
client can read and modify your finances and can forward them somewhere else:

1. Open `Settings`, find the MCP section and switch it on.
2. Accept the third-party warning.

Both settings (`mcp_enabled` and `mcp_third_party_ack`) must be set. Until
then `mira-cli mcp` exits with status `2` and prints why. Nothing else in the
CLI is affected.

### Running it

```bash
mira-cli --db ~/finanzas.db mcp
```

The process reads newline-delimited JSON-RPC from stdin and writes it to
stdout, one message per line. Warnings and errors go to stderr, so the
protocol channel stays clean. It runs until the client closes the stream.

Point an MCP client at the command, for example:

```json
{
  "mcpServers": {
    "mira": {
      "command": "mira-cli",
      "args": ["--db", "/home/you/finanzas.db", "mcp"]
    }
  }
}
```

### Tools

| Tool | Required | Optional |
| --- | --- | --- |
| `add_income` | `amount`, `account` | `description`, `category`, `date`, `note` |
| `add_expense` | `amount`, `account` | `description`, `category`, `date`, `note` |
| `transfer` | `source`, `target`, `amount` | `date`, `note` |
| `list_transactions` | none | `limit`, `account`, `since`, `until` |
| `report` | none | `since` |

Amounts are strings so that no rounding happens on the way in, and dates are
`YYYY-MM-DD`. Accounts are resolved by name.

Errors come back as JSON-RPC errors with a short reason: an account name that
does not exist says so instead of creating a second account. Unknown methods
return error `-32601`.

### What it does not do

The server has no chat, no LLM and no network access. It exposes the same five
local operations as the CLI subcommands above, and nothing else.