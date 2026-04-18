# Practical Workflows

## Flow 1: Record a daily expense

1. Go to **Transactions**.
2. Create an expense transaction.
3. Choose the account and category.
4. Save it.
5. Confirm the impact in **Dashboard**.

## Flow 2: Record monthly income

1. Create an income transaction.
2. Assign an income category such as salary.
3. Validate the destination account.
4. Save and review the updated balance.

## Flow 3: Transfer between accounts

1. Go to **Accounts**.
2. Use the transfer action.
3. Define source, destination, and amount.
4. If currencies differ, provide the exchange rate.

Expected result:
- One outgoing movement is registered in the source account.
- One incoming movement is registered in the destination account.

## Flow 4: Create an annual budget and load an initial proposal

1. Go to **Budgets**.
2. Create a new budget with code, year, and currency.
3. Use **Propose budget** to load an initial baseline from the last year with enough data.
4. Review and adjust the 12 months by category.
5. Confirm yearly totals for income, expense, and balance.

Expected result:
- An editable annual budget is available for income and expenses.
- If expenses exceed income, MIRA warns but does not block the budget.
- Internal savings categories do not appear as budgetable lines.

## Flow 5: Start-of-month recurring items

1. Configure recurring rules for fixed income and fixed expenses.
2. At the start of the month, run **Apply recurring**.
3. Confirm that retrying in the same period does not duplicate entries.

## Flow 6: Mid-month review

1. Open **Reports** and review totals.
2. Open **Budgets** and use **Compare against actuals**.
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
3. Open **Goals** and verify the linked goal increased.
4. Open **Reports** or **Budgets** and confirm the movement does not appear as real expense.

Expected result:
- The savings transfer remains traceable in transactions.
- The goal updates correctly.
- Operating expense and budget are not inflated by internal savings moves.

## Flow 9: Reconcile an account or credit card

1. Open the **Account Reconciliation** tool from the Accounts menu or by right-clicking an account.
2. Load your bank statement (Excel).
3. Review suggested matches and manually link any remaining transactions.
4. Verify the difference is zero and click **Conciliar** (Reconcile).

Expected result:
- The card or bank debt matches the statement.
- Transactions are marked as reconciled in the audit trail.
- Internal payments (transfers) do not inflate income or expense KPIs.

Reference:
- See **Account Reconciliation** for a detailed guide.
