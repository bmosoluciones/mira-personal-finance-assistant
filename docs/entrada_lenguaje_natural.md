# Natural Language

MIRA can capture actions from free text entered in the lower panel.

## How it works

General pipeline:

1. text normalization
2. interpretation by the active engine (deterministic or local LLM)
3. schema validation
4. action execution

If interpretation fails, MIRA does not stop the app. It shows a help message with examples instead.

## Supported actions

- `add_income`
- `add_expense`
- `report`
- `data_analysis`
- `none`

## Recommended examples

Income:

- "salary income 1200"
- "income 300 from sales"

Expense:

- "spent 25 on transport"
- "paid 80 for utilities"

Technical savings for goals:

- "saved 100 cordobas from change"
- "moved 300 dollars to savings from salary"
- "saved 50 dollars from my paycheck"

Important note:

- Savings phrases are stored as a technical outflow in an internal savings category so MIRA can update savings goals.
- That outflow is not treated as real consumption expense in reports, analysis, or budgets.
- Categories marked as savings do not appear as budgetable categories.

Reports:

- "show report"
- "show expense report"
- "analyze my last month data"

## Quick buttons

When the system answers with action `none`, quick actions appear for:

- Add Income
- Add Expense
- View Report

These buttons preload a template into the text box.

## Command history

Inside the input box you can use:

- Up arrow: previous command.
- Down arrow: next command or current draft.

## Assistant vs Chat

- `Assistant`: interprets and executes financial actions.
- `Chat`: free conversation with a local model.

Note:

- Chat is available only when a local LLM is ready.
- If there is no active model, MIRA falls back to the deterministic assistant parser.
