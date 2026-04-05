# Optional Local AI Models

MIRA does not need an LLM to record transactions or produce structured reports.

## What the local model does

A local GGUF model is used only for:

- chat mode
- conversational answers
- open-ended questions inside the app

## What the local model does not do

The local model does not participate in:

- recording income
- recording expenses
- parsing structured assistant prompts
- translating natural language into transactions

That always remains the job of `TransactionParserEngine`.

## How to enable it

1. If you are using an official release (`.exe` or `.zip`), open `Settings`.
2. Download or select a `.gguf` model.
3. Switch the interaction mode to `Chat`.

If you are building MIRA from the repository for development or packaging work, install the optional extra with:

```bash
pip install ".[chat]"
```

If there is no active model, MIRA automatically returns to assistant mode.
