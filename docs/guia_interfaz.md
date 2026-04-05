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

Categories are used to organize transactions by:

- income or expense type
- color
- parent and child hierarchy
- optional merge and cleanup flows

### Hierarchy and icons

- MIRA exposes a two-level hierarchy in the UI: a category can have one optional parent, but not grandchildren in the interface.
- When creating or editing a category, you can select an emoji or Unicode icon for the `Icon` field.
- The parent selector only shows categories of the same type and excludes the current category.
- Tables and selectors display both icon and parent-child relationship.

## Recurring view

Recurring transactions are templates for monthly movements.

- day of month
- transaction type
- account, amount, and category

Key action:

- `Apply recurring`: applies the rules for the current month only once per period.

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

Savings goals allow you to:

- create a goal with target amount and date
- record contributions
- track progress and remaining amount

Functional behavior:

- When savings are captured through natural language, MIRA records a technical outflow in a savings category.
- That movement updates the goal progress.
- The same movement is excluded from operating-expense reports and budget comparisons.

## Financial tools

From the `Tools` menu you can open calculators that run in memory without saving data automatically:

- `Compound Interest Calculator`
- `Loan Calculator`
- `Savings Goal Simulator`

## Settings view

Main settings include:

- user
- language
- theme
- default currency
- numeric separators
- preferred local AI model
- interaction mode (`Assistant` or `Chat` when a local LLM is active)
