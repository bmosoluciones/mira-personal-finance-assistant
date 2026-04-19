# Credit Cards

## What MIRA supports

MIRA handles a credit card as an account of type `credit`.

This means:

- each card purchase is recorded as a normal expense in that account
- each card payment is recorded as an internal transfer from a `bank` or `cash` account into the `credit` account
- card payments must not inflate income or expense KPIs
- refunds, cashback applied as credit, and positive adjustments can be recorded as income in the `credit` account

## How to record movements

### Card purchases

Record the purchase as an expense and choose the `credit` account.

Expected result:

- the card balance becomes more negative as debt increases
- the expense does appear in operating reports and expense KPIs

### Card payment

Use the `Credit Card Payment` option in `Transactions`.

Rules:

- source: only `bank` or `cash` accounts
- destination: only `credit` accounts
- the movement is stored as an internal transfer

Expected result:

- the source account balance decreases
- the card debt gets closer to zero
- no income or expense KPI is altered

### Refund, cashback, or positive adjustment

If the bank applies a monetary credit to the card, record it as income in the `credit` account.

Expected result:

- the debt decreases or the account turns positive if the credit exceeds what was owed
- the movement does count in income KPIs

## Recommended report

Use the `Account and Credit Card Balance` report to review:

- account name
- type
- currency
- current balance
- consolidated total

This report is useful to quickly validate whether bank, cash, and card balances match your actual financial position.

## Reconciling with the bank balance

MIRA does not perform automatic credit-card reconciliation. Reconciliation is manual and should be done by comparing your records against the statement or the balance published by the bank.

If you load the bank statement from Excel, MIRA accepts `.xlsx` files with headers in English or Spanish, including mixed combinations such as `Date`, `Referencia`, `Description`, `Income`, and `Gastos`.

### Base reconciliation rule

If the bank shows a statement debt of `12,350.00`, the `credit` account in MIRA should show approximately `-12,350.00` for the same date, unless you have a positive balance in your favor.

If the bank shows a positive balance, the MIRA card account can also be positive.

### Recommended step-by-step process

1. Identify the statement date or exact balance date you want to reconcile.
2. Open the correct `credit` account in MIRA.
3. Compare the MIRA balance and the bank balance for the same date.
4. If they differ, first review pending items or entries posted after the statement cutoff.
5. Then look for missing charges, duplicate charges, wrong payment dates, interest, fees, and missing refunds.
6. Correct missing items and compare again until the difference is zero or fully explained.

### Practical reconciliation order

Use this order because it reduces errors:

1. purchases in the period
2. payments applied before or on the statement date
3. recurring charges
4. interest
5. fees and similar charges
6. refunds, cashback, and credit notes

### Typical differences between bank and system

Most differences come from:

- a purchase already recorded in MIRA but not yet posted by the bank
- a bank charge or adjustment that has not been recorded yet
- a payment recorded with a different date than the bank application date
- a payment recorded against the wrong account
- the same charge captured twice
- a missing refund or credit note
- missing interest or end-of-cycle fees

## How to identify recurring charges

Recurring charges are often the first source of small but persistent differences.

Look for these patterns:

- the same merchant every month
- the same or very similar amount
- a close date in each cycle
- descriptions such as streaming, subscription, membership, insurance, phone, internet, cloud, app store, gym, or platform

How to record them:

- always as an expense in the `credit` account
- ideally with a clear merchant description
- if they repeat, use a consistent category and optionally a tag such as `automatic`

If a recurring charge appears every month and should always be recorded, recurring templates can help. If the bank moves the charge date often, it is safer to record it when it actually appears on the statement.

## Interest

Interest is not a card payment. It is a financial cost and must be recorded as an expense in the `credit` account.

Good practices:

- use a dedicated category such as `interest`, `finance_charges`, or similar
- record the exact amount charged by the bank
- use the statement or bank-posted date

Do not record interest as a transfer or a payment.

## Fees and similar charges

Fees should also be recorded as expense in the `credit` account.

This group includes:

- annual membership
- late fees
- cash advance fees
- conversion or international purchase fees
- administrative charges
- insurance added by the bank
- SMS, alerts, or related services charged to the card

Recommendation:

- use a separate category such as `card_fees` or `bank_fees`
- if you need more detail, use a subcategory or note

## Suggested monthly close routine

1. Wait until you have the statement or statement balance.
2. Open the correct card in MIRA.
3. Review large purchases first.
4. Review recurring charges.
5. Record interest.
6. Record fees.
7. Verify refunds or cashback.
8. Run the card payment if it already happened.
9. Confirm that the `credit` account balance matches the bank balance.

## Warning signs

Review immediately if you notice any of these situations:

- bank and MIRA balances diverge every month
- the difference is always the same amount
- a card payment changes the expense or income KPI
- the card appears with a positive balance when there is no credit in your favor
- there are bank charges you cannot trace in the audit trail

When that happens, review recurring charges, interest, fees, refunds, and payment dates first.
