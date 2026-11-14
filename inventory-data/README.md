# Inventory demo dataset

`inventory/inventory_data.json` is the system of record for the ERP demo. A
pristine copy is kept as `inventory/inventory_data.seed.json`; the application
only ever writes the first file.

```text
inventory-data/
└── inventory/
    ├── inventory_data.json        # working dataset (mutated by approved tools)
    └── inventory_data.seed.json   # pristine baseline for restoring the demo
```

## Fictional data notice

Every person, company, email address, telephone number, address, and transaction
is fictional. The company (BAYAZID Distribution Ltd) does not exist. Currency is
**BDT**, dates use **YYYY-MM-DD**, and the operating timezone is
**Asia/Dhaka**.

## Metadata

| Field | Value |
| --- | --- |
| Dataset name | BAYAZID Distribution Ltd — ERP Inventory Demo |
| Version | 1.0.0 |
| Currency | BDT |
| Date format | YYYY-MM-DD |
| Timezone | Asia/Dhaka |
| Last updated | 2026-11-14T09:00:00+06:00 |

`metadata.last_updated` is refreshed on every successful write.

## Entity counts

| Collection | Rows | Notes |
| --- | ---: | --- |
| `categories` | 10 | Electronics, Computers, Accessories, Networking, Office Supplies, Furniture, Printers, Storage, Power & UPS, Stationery |
| `units` | 5 | Piece, Box, Pack, Carton, Set |
| `products` | 36 | 30+ products with unique SKUs, mixed price ranges and stock conditions |
| `suppliers` | 9 | Payment terms, outstanding balances |
| `customers` | 18 | Individuals and businesses, varied credit limits |
| `employees` | 10 | Sales, operations, finance, procurement, IT; `manager_id` forms a tree |
| `warehouses` | 3 | Dhaka Main, Chattogram Branch, Sylhet Distribution |
| `stock` | 78 | Per product/warehouse; reserved never exceeds on-hand |
| `stock_movements` | 52 | Receipts, sales, adjustments, transfers, returns |
| `sales` | 18 | All statuses represented, including draft and pending approval |
| `sale_items` | 38 | Line totals match quantity × unit price |
| `invoices` | 13 | Paid, partially paid, unpaid, overdue |
| `payments` | 13 | Cash, bank transfer, mobile banking, card |
| `purchase_orders` | 9 | Includes pending-approval and received orders |
| `purchase_order_items` | 18 | PO totals match their items |
| `accounts` | 14 | Assets, liabilities, equity, revenue, expenses |
| `expenses` | 10 | Draft, pending, approved, rejected, paid |
| `journal_entries` | 5 | Every posted entry balances |
| `sales_targets` | 10 | Monthly targets for two sales representatives |
| `returns` | 5 | pending_review, approved, rejected, processed |
| `approvals` | 8 | PO, expense, discount, stock-adjustment, and return approvals |
| `audit_log` | 12 | Sensitive-operation history |
| `operation_log` | 0 | Filled by approved sensitive tool executions |

## Interconnections

- Products reference a category, a unit, and a supplier.
- Stock rows reference a product and a warehouse; the pair is unique.
- Stock movements reference a product, a warehouse, and an employee. `sale`,
  `purchase_receipt`, and `sales_return` references must resolve to a sale, a
  purchase order, or a return respectively.
- Sales reference a customer, a sales employee, and a warehouse. Sale items link
  products to sales.
- Invoices link one sale to one customer; payments link back to the invoice and
  customer.
- Purchase orders reference a supplier, warehouse, and the creating employee.
  Purchase-order items link products to orders.
- Journal lines reference accounts. Posted entries must have equal debits and
  credits.
- Expenses reference an expense account, a submitter, and an optional approver.
- Returns reference the original sale, customer, and product.
- Approvals reference the resource they concern and the requesting/assigned
  employees.
- Audit entries reference an employee or a system actor
  (`HUMAN_OPERATOR`, `AI_AGENT`, `SYSTEM`).

## Consistency guarantees

The dataset is validated as a whole on load and on every write. Guarantees
include:

- unique primary IDs and SKUs
- valid foreign keys everywhere
- `sale.subtotal` equals its line items; `sale.total = subtotal - discount + tax`
- invoice `amount_paid + balance_due = total` and matches completed payments
- each customer's `outstanding_balance` equals their open invoice balances
- purchase-order totals equal their items
- posted journal entries balance
- `quantity_reserved <= quantity_on_hand` and available quantity is never negative

Validation never repairs data. An invalid file is reported, and a write that
would create an inconsistency is aborted.

The application caps `operation_log` and `audit_log` with
`INVENTORY_OPERATION_LOG_LIMIT` and `INVENTORY_AUDIT_LOG_LIMIT`; appends keep the
newest entries and drop the oldest. The configured reviewer identity
(`INVENTORY_OPERATOR_ID`) is written to `audit_log.actor_id`.

## Restoring the demo

Approved tools mutate `inventory_data.json`. Reset it at any time:

```bash
cp inventory-data/inventory/inventory_data.seed.json \
   inventory-data/inventory/inventory_data.json
```

The running CLI reads the file at startup and reloads it for every mutation, so a
restore takes effect on the next tool call. If the dataset is missing, the
application starts without inventory tools and logs a warning instead of
crashing.
