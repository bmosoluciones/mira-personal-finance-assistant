# Import, Export and Backup

## Import transactions

Menu path:

- `File -> Import transactions...`

Import rules:

- each valid row is inserted as a transaction
- invalid rows are skipped and counted as errors
- if an account does not exist, it is created automatically
- the file picker accepts `.csv` and `.xlsx`
- `.xls` and any other extension are rejected explicitly
- import headers may be in English or Spanish, and mixed files are accepted

Expected transaction fields:

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

Accepted header aliases include:

- `date` / `fecha`
- `type` / `tipo`
- `amount` / `monto`
- `account_name` / `account` / `cuenta` / `nombre_cuenta`
- `category` / `categoria`
- `subcategory` / `subcategoria`
- `payment_method` / `metodo_pago` / `medio_pago`
- `description` / `descripcion`
- `note` / `nota`
- `receipt_path` / `ruta_recibo` / `ruta_comprobante` / `comprobante`
- `tags` / `etiquetas`

Notes:

- `type` and `amount` are the only required transaction columns.
- if `account_name` is missing, MIRA uses `General`
- Excel imports read the workbook in `.xlsx` format only

## Export transactions

Menu path:

- `File -> Export transactions...`

Export content:

- includes transactions with the system's standard columns
- can be used for external analysis or historical control
- the save dialog accepts `.csv` and `.xlsx`
- if no extension is provided, MIRA saves `.csv` by default
- if the Excel filter is selected and no extension is provided, MIRA saves `.xlsx`
- Excel exports are written to a worksheet named `Transactions`

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
2. Export monthly CSV or XLSX for audit purposes.
3. Create an additional backup before upgrading MIRA.
