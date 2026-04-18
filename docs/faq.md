# FAQ

## Does MIRA need internet access to work?

No. MIRA works offline for its main financial operations.

## Does my data leave my device?

No. By design, the database is local and the main processing runs entirely on your machine.

## Can I use MIRA without AI models?

Yes. MIRA includes a built-in deterministic parser that allows you to use natural language without requiring a Large Language Model (LLM).

## What is the difference between Assistant and Chat?

- **Assistant**: Interprets and executes structured financial actions (e.g., adding expenses).
- **Chat**: A free-form conversation mode that requires an optional local GGUF model to be active.

## Where is my database stored?

The default path follows standard platform conventions (XDG on Linux). For example:
- Linux: `~/.local/share/mira/mira.db`
- Windows: `%LOCALAPPDATA%\mira\mira.db`

You can specify a custom path using the `--db PATH` flag.

## How do I avoid losing information?

1. Use the **Backup** tool in the File menu regularly.
2. Export your transactions to **CSV** for external records.
3. Always verify a backup file before performing a **Restore**.

## Can I use MIRA on Windows?

Yes. MIRA provides a standard `.exe` installer and a portable `.zip` version for Windows.
