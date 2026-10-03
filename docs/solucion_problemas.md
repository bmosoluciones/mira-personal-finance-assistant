# Troubleshooting

## The app does not start

Checklist:

1. Verify that `PySide6` is installed.
2. Run `mira-cli --debug` to inspect traces.
3. If you are using a virtual environment, confirm that it is activated.

## Natural language commands are not recognized

Common causes:

- the sentence is too ambiguous
- the amount is missing for income or expense
- the local model is not available when you are expecting chat behavior

Actions:

1. Use more direct phrases.
2. Confirm the account or category exists, or let MIRA resolve it from context.
3. Check that you are in `Assistant` mode instead of `Chat` when no LLM is active.

## Chat does not appear or does not respond

- Chat mode requires a configured AI provider.
- Without a provider (and model) in `Settings`, only `Assistant` mode is available.

Quick review:

1. Confirm the provider, base URL and model are set in `Settings`.
2. Confirm the API key was saved and the third-party notice was accepted when the endpoint is not local.
3. Review logs with `--debug`.
## CSV import fails

Typical causes:

- `type` is not `income` or `expense`
- `amount` is not numeric or is less than or equal to zero
- the file has incomplete columns

Solution:

1. Validate the file headers.
2. Fix invalid rows and try again.

## Reports do not show what you expect

1. Review active filters.
2. Verify the date range.
3. Confirm the transactions are assigned to the correct account and category.

## I restored a backup and lost recent changes

Expected behavior: restore replaces the current content.

Mitigation:

1. Keep versioned backups.
2. Create a backup before restoring another file.
