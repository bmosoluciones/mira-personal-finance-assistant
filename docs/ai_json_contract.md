# AI JSON Contract -> Backend -> Frontend

This document defines the official JSON format accepted by the system to interpret natural language instructions and convert them into financial actions.

> This schema is the integration contract between backend and frontend. Any change must update this document and be versioned.

## 1) Accepted JSON schema

```json
{
  "action": "add_income | add_expense | report | data_analysis | none",
  "amount": 1000.0,
  "description": "Salary",
  "category": "salary",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 1.0,
  "converted_amount": 1000.0,
  "report_type": "expenses | incomes | balance | cashflow | summary | null",
  "period": {
    "preset": "this_month | last_month | last_3_months | this_year | custom",
    "from": "2025-01-01",
    "to": "2025-03-31"
  },
  "filters": {
    "categories": ["restaurant"],
    "accounts": ["General"],
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": "Income recorded: 1000.00 USD (base USD) in General"
}
```

## 2) Field definitions

- `action` *(string, required)*
  - Allowed values:
    - `add_income`: record income
    - `add_expense`: record expense
    - `report`: request a report
    - `data_analysis`: request user data analysis
    - `none`: no executable action

- `amount` *(number, optional depending on action)*
  - Original amount detected in the prompt.
  - Required for `add_income` and `add_expense`.
  - Since `0.0.1a2`, the backend normalizes monetary numbers as exact two-decimal money values before persistence.

- `description` *(string, optional)*
  - Free operation description, such as `Salary` or `Coffee`.

- `category` *(string, optional)*
  - Semantic category such as `salary`, `food`, or `transport`.

Special rule for savings:

- If the AI or deterministic parser interprets a savings phrase, the action still remains `add_expense`.
- In that case `category` can resolve to a technical savings category such as `savings` or its internal canonical equivalent.
- Categories internally marked as savings update goals but are excluded from real expense in reports, analysis, and budgets.

- `account` *(string, optional)*
  - Destination or source account such as `General`, `Savings`, or `Cash`.

- `base_currency` *(string, required for monetary flows)*
  - System base currency used to consolidate the ledger.

- `exchange_rate` *(number, required for monetary flows)*
  - Exchange rate used to convert `amount` into `base_currency`.
  - Rule: `converted_amount = amount * exchange_rate`.
  - One action supports only one FX leg into `base_currency`. If a real flow crosses more than two currencies, the caller must provide the final effective rate into `base_currency` or split the flow into multiple operations.

- `converted_amount` *(number, required for monetary flows)*
  - Amount converted into the base currency.
  - It must match the conversion formula after applying the canonical rounding rule.

### Fields specific to `report` and `data_analysis`

- `report_type` *(string, required when `action=report`)*
  - Allowed values: `expenses`, `incomes`, `balance`, `cashflow`, `summary`.

- `period` *(object, required when `action=report` or `action=data_analysis`)*
  - `preset`: `this_month`, `last_month`, `last_3_months`, `this_year`, `custom`
  - `from`: required when `preset=custom`
  - `to`: required when `preset=custom`

- `filters` *(object, optional when `action=report` or `action=data_analysis`)*
  - `categories`: included categories
  - `accounts`: included accounts
  - `min_amount`: minimum threshold
  - `max_amount`: maximum threshold
  - `text`: free-text search

- `message` *(string, optional but recommended)*
  - Friendly message for UI or logs.

## 3) Validation rules

1. If `action` is `add_income` or `add_expense`, `amount`, `base_currency`, `exchange_rate`, and `converted_amount` must be present.
2. If `action` is `report`, `report_type` and `period` are mandatory.
3. If `action` is `data_analysis`, `period` is mandatory and `report_type` must be `null`.
4. If `action` is `none`, monetary and report fields may be omitted and `message` should explain why no action is executed.
5. `exchange_rate` must be greater than zero for monetary operations.
6. `converted_amount` must respect the conversion formula.
7. Monetary values (`amount`, `converted_amount`, `filters.min_amount`, `filters.max_amount`) are normalized to two decimals using `ROUND_HALF_UP`.
8. If `period.preset = custom`, `period.from` and `period.to` are mandatory.
9. If `action = add_expense` and the category is internally marked as savings, the backend must treat the operation as a technical outflow for goals and exclude it from reportable real expense.

## 4) Monetary semantics

- JSON still carries money as JSON numbers.
- At validation time, the backend converts monetary values to exact decimal semantics with two decimals.
- SQLite persistence stores the resulting values as integer cents.
- UI, charts, and some export adapters may render decimal strings or display floats, but arithmetic and persistence do not rely on binary-floating calculations.
- Canonical rounding rule: `ROUND_HALF_UP` to two decimals.

## 5) Valid examples

### Example A: Income in base currency

```json
{
  "action": "add_income",
  "amount": 1000.0,
  "description": "Salary",
  "category": "salary",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 1.0,
  "converted_amount": 1000.0,
  "report_type": null,
  "period": null,
  "filters": null,
  "message": "Income recorded: 1000.00 USD (base USD) in General"
}
```

### Example B: Expense in a different currency

```json
{
  "action": "add_expense",
  "amount": 500.0,
  "description": "Food expense",
  "category": "food",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 0.058,
  "converted_amount": 29.0,
  "report_type": null,
  "period": null,
  "filters": null,
  "message": "Expense recorded: 500.00 (converted to 29.00 USD) in General"
}
```

### Example C: Report with type, period, and filter

```json
{
  "action": "report",
  "amount": null,
  "description": "Expense report",
  "category": null,
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": "expenses",
  "period": {
    "preset": "last_3_months",
    "from": null,
    "to": null
  },
  "filters": {
    "categories": ["restaurant"],
    "accounts": null,
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": "Requested expenses report for restaurants in last 3 months"
}
```

### Example D: Data analysis

```json
{
  "action": "data_analysis",
  "amount": null,
  "description": null,
  "category": "education",
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": null,
  "period": {
    "preset": "last_3_months",
    "from": null,
    "to": null
  },
  "filters": {
    "categories": ["education"],
    "accounts": null,
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": null
}
```

## 6) Recommended system prompt

```text
You are a financial parser. Convert the user's prompt into valid JSON.
Reply with JSON only and include these keys:
action, amount, description, category, account, base_currency, exchange_rate, converted_amount, report_type, period, filters, message.

Rules:
- action in {add_income, add_expense, report, data_analysis, none}
- For add_income/add_expense:
  - amount, base_currency, exchange_rate, and converted_amount are required
  - converted_amount = amount * exchange_rate rounded to 2 decimals with ROUND_HALF_UP
  - report_type, period, and filters must be null
- For report:
  - report_type required in {expenses, incomes, balance, cashflow, summary}
  - period required with preset in {this_month,last_month,last_3_months,this_year,custom}
  - if period.preset=custom, from and to are required
  - filters optional
- For data_analysis:
  - period required
  - filters optional
  - report_type must be null
- For none:
  - monetary and report fields may be null
- Do not add any text outside the JSON
```

## 7) Compatibility

- This document replaces the previous format that did not include multi-currency fields, explicit report structure, or the `data_analysis` action.
- Backend and frontend must validate the presence and consistency of `base_currency`, `exchange_rate`, `converted_amount`, `report_type`, `period`, and `filters`.
- Since `0.0.1a2`, developer-facing integrations must also respect the exact-money contract:
  - money fields are normalized to two-decimal exact values
  - `converted_amount` is validated against the rounded conversion formula
  - multi-leg currency conversions are not represented in a single action
