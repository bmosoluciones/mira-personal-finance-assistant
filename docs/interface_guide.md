# Interface Guide

The main MIRA window is composed of:

- a top menu bar
- a side navigation bar
- a central workspace
- a lower chat and command panel

## Side navigation

Main sections:

- Dashboard
- Transactions
- Accounts
- Budgets
- Categories
- Recurring
- Reports
- Goals
- Settings

## Main menu

Frequent actions:

- `File`: import CSV, export CSV, backup, restore, exit.
- `Accounts`: add account.
- `Transactions`: add transaction.
- `Budget`: create annual budget.
- `Categories`: add income or expense categories.
- `Recurring`: add and apply recurring entries.
- `Reports`: open reports and analyze data.
- `Goals`: create a goal and contribute to it.
- `View`: show or hide the sidebar and prompt panel.
- `Settings`: open the main settings view.

## Useful shortcuts

- `Ctrl+Q`: quit.
- `Ctrl+B`: toggle the sidebar.
- `Ctrl+P`: toggle the prompt panel.
- `Ctrl+,`: open settings.

## Transactions view

This view lets you:

- create, edit, delete, and duplicate transactions
- filter by date, category, account, and text
- review totals for the filtered set

Special visual indicators:

- `+ income` in green for income
- `- expense` in red for operating expense
- `@ savings` in blue for technical savings outflows

Bottom summary:

- It shows four cards: Income, Expense, Net, and Savings.
- `@ savings` movements accumulate in Savings and are not added to operating expense.

Relevant fields:

- date
- type (`income` or `expense`)
- amount
- account
- category and subcategory
- payment method
- note
- receipt path

## Accounts view

This area manages financial accounts:

- create, edit, and delete accounts
- current balance per account
- currency attached to each account

It also supports account-to-account transfers, including currency conversion when needed.

## Budgets view

The Budgets view works with annual budgets stored in the database.

Main elements:

- budget selector by code
- new budget form with code, year, and currency
- annual table by category with 12 months plus yearly total
- summary cards for total income, total expense, and planned balance
- visible warning when expected expenses exceed expected income without blocking the budget

Available actions:

- new budget
- delete budget
- propose budget
- compare against actuals
- monthly budget tracking

Propose budget:

- Uses the latest year with enough history.
- Calculates an initial monthly average per category.
- If there is not enough history, MIRA informs the user and does not generate a proposal.

Compare against actuals:

- Supports yearly, half-year, quarterly, and monthly views.
- Quarterly is the default comparison.
- Shows Actual, Budget, and Variance per period and for the full year.
- Distinguishes when income or expense is better or worse than expected.

Monthly tracking:

- Lets you inspect any month from the selected budget year.
- Displays global KPIs for Assigned, Executed, and Available.
- Shows expense categories with Assigned, Executed, Available, and visual state.
- Supports reallocating funds between categories without changing the monthly total.

Special savings rule:

- Categories internally marked as savings are not shown as budget lines.
- Transactions used to feed savings goals do not count as operating expense in actual-vs-budget comparison.

Currency:

- Each budget has its own currency.
- If a real transaction cannot be reconciled to the budget currency, it is excluded and the UI reports that exclusion.

## Categories view

Organize your financial movements through a logical category structure.

- **Type**: Classify as Income or Expense.
- **Hierarchy**: Supports two levels (Parent and Child). The parent selector only shows categories of the same type.
- **Personalization**: Assign colors and Unicode emojis/icons for quick visual identification.
- **Merge**: Consolidate two categories into one, automatically moving all transactions and history. Useful for data cleanup.
- **Advanced Linking**: Using the **🔗 Link** button, you can associate income categories with specific expenses for profitability analysis in the Master Report.

### Hierarchy and icons

- MIRA restricts the UI to two levels to maintain clarity, even if the engine supports more depth.
- Icons are displayed in all tables, reports, and the transaction selector to facilitate rapid entry.

## Recurring view

Recurring transactions are templates for recurring monthly movements such as rent, subscriptions, or salaries.

- **Day of month**: The day the transaction usually occurs.
- **Transaction type**: Income or Expense.
- **Details**: Account, amount, category, and tags.

Key action:

- **Apply recurring**: Scans all active recurring templates and generates real transactions for the current month. MIRA prevents duplicates by checking if a recurring template has already been applied in the current period.

## Tags view

Tags allow for cross-categorical organization of transactions (e.g., #vacation, #business).

- **Create and Manage**: Add tags with custom colors and icons.
- **Usage**: Assign multiple tags to a single transaction to enable multi-dimensional filtering.
- **Analysis**: Use tags in reports to see spending patterns that span multiple categories.

## Reports view

Includes:

- total income vs expenses
- category breakdown
- account trend
- cash flow
- user data analysis when applicable

Special savings rule:

- Transactions in categories marked as savings do not count as operating expense.
- They also stay out of analytical expense breakdowns focused on consumption.

## Dashboard view

KPI cards:

- Income
- Expense
- Net
- Savings

Calculation rule:

- Savings is calculated separately using categories internally marked as savings.
- Expense represents operating consumption and excludes technical savings outflows.

## Goals view

Savings goals allow you to plan for specific financial objectives with real-time progress tracking.

- **Configuration**: Define a name, target amount, and deadline.
- **Automatic Link**: Each goal is linked to a technical "savings outflow" category.
- **Contributions**: Use the **💰 Contribute** button to record deposits toward the goal.
- **Traceability**: Shows completion percentage, amount saved, and remaining balance.

### Business rules for goals

- Movements toward goals (technical outflows) update the goal progress.
- These movements are excluded from operating expense reports and real-vs-budget comparisons to avoid distorting real consumption.

## Financial tools

From the `Tools` menu you can open calculators that run in memory without saving data automatically:

- **Compound Interest Calculator** to project capital growth.
- **Loan Calculator** for amortization using French and German methods.
- **Savings Goal Simulator** to test scenarios and optionally pre-fill the goal creation form.

## Settings view

Main settings include:

- user
- language
- theme
- default currency
- numeric separators
- preferred local AI model
- interaction mode (`Assistant` or `Chat` when a local LLM is active)
