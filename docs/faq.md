# FAQ

## Does MIRA need internet access to work

No. MIRA works offline for its main financial operations.

## Does my data leave my device

No under the normal usage model. The database is local and the main processing can run without network access.

## Can I use MIRA without AI models

Yes. It includes a deterministic parser for natural language input.

## What is the difference between Assistant and Chat

- `Assistant` executes structured financial actions.
- `Chat` is free conversation and needs a ready local LLM.

## Where is my database stored

Default path: the platform/XDG application-data directory, for example `~/.local/share/mira/mira.db` on Linux.

You can change it with `--db` when launching the app.

As of `0.0.1a2`, MIRA no longer scans or copies databases from the legacy `~/.mira/` location during startup.

## How do I avoid losing information

1. Create SQLite backups regularly.
2. Export CSV periodically.
3. Verify the file before restoring.

## Can I use MIRA on Windows

Yes. There is a GUI launcher (`mira`) and a CLI entry point (`mira-cli`).
