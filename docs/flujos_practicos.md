# Practical Workflows

## Flow 1: Record a daily expense

1. Go to `Transactions`.
2. Create an expense transaction.
3. Choose the account and category.
4. Save it.
5. Confirm the impact in `Dashboard`.

## Flow 2: Record monthly income

1. Create an income transaction.
2. Assign an income category such as salary.
3. Validate the destination account.
4. Save and review the updated balance.

## Flow 3: Transfer between accounts

1. Go to `Accounts`.
2. Use the transfer action.
3. Define source, destination, and amount.
4. If currencies differ, provide the exchange rate.

Expected result:

- one outgoing movement is registered in the source account
- one incoming movement is registered in the destination account

## Flow 4: Create an annual budget and load an initial proposal

1. Go to `Budgets`.
2. Create a new budget with code, year, and currency.
3. Use `Propose budget` to load an initial baseline from the last year with enough data.
4. Review and adjust the 12 months by category.
5. Confirm yearly totals for income, expense, and balance.

Expected result:

- an editable annual budget is available for income and expenses
- if expenses exceed income, MIRA warns but does not block the budget
- internal savings categories do not appear as budgetable lines

## Flow 5: Start-of-month recurring items

1. Configure recurring rules for fixed income and fixed expenses.
2. At the start of the month, run `Apply recurring`.
3. Confirm that retrying in the same period does not duplicate entries.

## Flow 6: Mid-month review

1. Open `Reports` and review totals.
2. Open `Budgets` and use `Compare against actuals`.
3. Review category variances in quarterly or monthly view.
4. Adjust the budget or categories according to findings.
5. Export CSV for external analysis if needed.

## Flow 7: Monthly close

1. Run the main reports.
2. Compare actuals vs budget for the period.
3. Verify savings-goal progress.
4. Create a database backup.
5. Save the month's transaction CSV.

Operational note:

- If you recorded savings from natural language, those movements still push goal progress.
- They should not be read as real consumption expense in reports or as budget variance.

## Flow 8: Record savings without distorting expense

1. Use a phrase like "saved 50 dollars for emergencies".
2. Confirm that the transaction is stored as a technical savings outflow.
3. Open `Goals` and verify the linked goal increased.
4. Open `Reports` or `Budgets` and confirm the movement does not appear as real expense.

Expected result:

- the savings transfer remains traceable in transactions
- the goal updates correctly
- operating expense and budget are not inflated by internal savings moves

## Flow 9: Reconcile a credit card

1. Record purchases in the `credit` account.
2. Record the payment using `Credit Card Payment`, not as a normal expense.
3. Open the account and credit-card balance report.
4. Compare the MIRA balance against the bank balance for the same date.
5. Review recurring charges, interest, fees, and refunds that may be missing.

Expected result:

- the card debt matches the statement
- payments do not inflate the expense KPI
- financial charges remain traceable inside the same card account

Reference:

- See `Credit Cards` for a detailed reconciliation guide.
