# Account Reconciliation

## Overview

Account reconciliation in MIRA allows you to compare your internal records against an external bank statement (Excel) to ensure your balance is accurate and no transactions are missing.

## Accessing Reconciliation

You can open the reconciliation tool in two ways:

1. **Accounts Sidebar**: Go to the **Accounts** section, right-click on the account you want to reconcile, and select **✓ Reconcile**.
2. **Main Menu**: Go to **Accounts** -> **Reconcile account**.

## Reconciliation Workflow

### 1. Load the External Statement

1. Click **Load Excel**.
2. Select your bank statement file (`.xlsx`).
3. MIRA will extract the transactions and display them in the **External Transactions** table (left).

### 2. Review Automatic Matches

MIRA automatically suggests matches when it finds a system transaction and an external transaction with:
- The exact same amount.
- A close date (within a few days).

Suggested matches are highlighted, allowing you to quickly verify them.

### 3. Manual Matching

If a transaction wasn't automatically matched:
1. Select one or more rows from the **External Transactions** table.
2. Select the corresponding transaction(s) from the **System Transactions** table (right).
3. Verify that the **Matched Difference** is zero.
4. Click **Conciliar** (Reconcile).

### 4. Handling Differences

If the selected amounts do not match, MIRA will show a warning with the calculated difference. You can still proceed if the difference is explained (e.g., small bank fees not yet recorded).

### 5. Finalizing

Once all items are reconciled, the **System Transactions** will be marked as "reconciled" in the main transactions view, and the account balance should match your bank statement.

## Clearing Reconciliation

If you made a mistake:
1. Select the reconciled system transactions.
2. Click **Quitar conciliacion** (Clear reconciliation).

## Summary Cards

The top of the reconciliation window shows:
- **External Summary**: Opening balance, total income, total expenses, and closing balance from the Excel file.
- **System Summary**: Corresponding totals from your MIRA records for the same period.
- **Difference**: The current gap between your system records and the external statement.
