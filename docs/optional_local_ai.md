# Optional AI Chat

MIRA does not need an LLM to record transactions or produce structured reports.

## What chat mode does

The optional chat mode is used only for:

- chat mode
- conversational answers
- open-ended questions inside the app

## What chat mode does not do

Chat mode does not participate in:

- recording income
- recording expenses
- parsing structured assistant prompts
- translating natural language into transactions

That always remains the job of `TransactionParserEngine`.

## How to enable it

1. Open `Settings` and choose an AI provider.
2. Enter the base URL, model name and API key (an OpenAI-compatible endpoint or Anthropic).
3. Accept the third-party notice when the endpoint is not local.
4. Switch the interaction mode to `Chat`.

Remote OpenAI-compatible endpoints must use HTTPS so chat text and API keys are
encrypted in transit. Plain HTTP is allowed only for loopback endpoints such as
`localhost`. Anthropic uses its fixed HTTPS endpoint.

Chat requests are only sent when you use chat mode. The API key is stored next
to the database in `llm-secrets.json` with `0600` permissions and is never part
of a backup.

If no provider is configured, MIRA automatically returns to assistant mode.

The command line and the MCP server are documented separately. See [Command Line and MCP Server](command_line.md).
