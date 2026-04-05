# Import, Export and Backup

## Import CSV

Menu path:

- `File -> Import CSV...`

Import rules:

- each valid row is inserted as a transaction
- invalid rows are skipped and counted as errors
- if an account does not exist, it is created automatically

Expected CSV fields:

- `date`
- `type` (`income` or `expense`)
- `amount`
- `account_name`
- `category`
- `subcategory`
- `payment_method`
- `description`
- `note`
- `receipt_path`

## Export CSV

Menu path:

- `File -> Export CSV...`

Export content:

- includes transactions with the system's standard columns
- can be used for external analysis or historical control

## Database backup

Menu path:

- `File -> Backup Database...`

Behavior:

- creates a full SQLite copy
- does not allow overwriting the active database file itself

Good practices:

1. Keep a weekly backup.
2. Preserve at least the latest 4 versions.
3. Store a copy outside the main device when possible.

## Restore database

Menu path:

- `File -> Restore Database...`

Behavior:

- validates that the selected file is a compatible MIRA backup before replacing the active database
- restores through a staged database swap and reconnects the runtime afterwards
- reports when a supported schema upgrade was applied during restore
- it is recommended to close pending workflows before restoring

## Recommended continuity strategy

1. Create a backup before large imports.
2. Export monthly CSV for audit purposes.
3. Create an additional backup before upgrading MIRA.
