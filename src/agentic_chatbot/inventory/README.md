# Inventory module (ERP demo)

This package adds a practical ERP-style inventory domain to BAYAZID AI. It is
deliberately small and additive: the existing chat graph, SQLite checkpointing,
RAG stack, and CLI are unchanged.

The point is to practise:

- AI-agent tool calling and tool selection
- Human-in-the-Loop (HITL) approval for sensitive operations
- LangGraph `interrupt()` / `Command(resume=...)`
- Edit-before-execute workflows
- Idempotent business operations and audit logging

## Layout

```text
inventory/
├── data_access.py   # InventoryStore: load, lock, validate, atomic save
├── validation.py    # validate_dataset(): IDs, FKs, financial, inventory rules
├── service.py       # InventoryService: business rules and workflows
├── approvals.py     # SENSITIVE_TOOLS: name -> human-facing action title
└── tools/
    ├── _helpers.py  # JSON/error/operation-id helpers
    ├── catalog.py   # products and categories
    ├── stock.py     # stock levels, adjustments, transfers, movements
    ├── parties.py   # customers and suppliers
    ├── sales.py     # sales, invoices, payments
    ├── procurement.py
    ├── finance.py   # accounts, expenses, summaries
    └── workflows.py # returns and seeded approvals
```

Dependency direction:

```text
tools/*  ->  service.py  ->  data_access.py  ->  validation.py
                     \->  inventory-data/inventory/inventory_data.json
```

Tools never read or write JSON directly. The service never prints. The CLI never
touches the store. Presentation details live in `cli/`.

## Data flow

1. The model selects a tool.
2. LangGraph routes read-only tools to `ToolNode`. Sensitive tools go to the
   `approval` node, which calls `interrupt()` and pauses.
3. After a human decision, the approval node invokes the tool with an
   `inventory_operation_id` injected through `RunnableConfig`.
4. The tool calls `InventoryService`.
5. The service opens an `InventoryStore.transaction()`: read the latest file,
   mutate a copy, run the full validator, then atomically `os.replace()` the
   file. The mutation and its idempotency record commit together.
6. The tool returns a JSON string (or an `Error: ...` string) to the model.

## Dataset

The system of record is
`inventory-data/inventory/inventory_data.json`. A pristine baseline is kept at
`inventory_data.seed.json` next to it. Restore with:

```bash
cp inventory-data/inventory/inventory_data.seed.json \
   inventory-data/inventory/inventory_data.json
```

Every write updates `metadata.last_updated` in `Asia/Dhaka` time. All people,
companies, contacts, and transactions are fictional.

### Entity relationships

```text
categories ── parent_category_id ──────────────┐
    │                                          │
units ── products ── suppliers                  │
            │   │                                │
            │   └── stock ── warehouses ── employees
            │                   │
            │                   └── stock_movements ── reference -> sales /
            │                                          purchase_orders / returns
            ├── sale_items ── sales ── customers / employees / warehouses
            ├── purchase_order_items ── purchase_orders ── suppliers / employees
            └── returns ── sales / customers

invoices ── sales / customers
payments ── invoices / customers

accounts ── journal_entries ── lines[].account_id
accounts ── expenses ── employees (submitted_by / approved_by)

approvals ── purchase_orders / expenses / sales / stock_movements / returns
audit_log ── employees (or HUMAN_OPERATOR / AI_AGENT / SYSTEM)
operation_log ── idempotency records for sensitive tool executions
```

## Business rules

### Stock

- `available = quantity_on_hand - quantity_reserved`
- Reserved quantity cannot exceed on-hand quantity.
- Adjustments cannot make on-hand or available negative.
- Transfers require sufficient available stock at the source and write a
  `transfer_out` plus `transfer_in` movement with one shared reference.
- Low stock means total available `<= reorder_level`. Zero available is
  out-of-stock.

### Sales

- `line_total = quantity * unit_price`
- `subtotal = sum(line_total)`
- `tax = round_half_up((subtotal - discount) * 5%)`
- `total = subtotal - discount + tax`
- New sales are `draft` or `pending_approval`; stock is not deducted until the
  sale is `confirmed`.
- Confirming deducts stock and writes `sale` movements.
- Only confirmed sales can be invoiced; each sale has at most one invoice.
- A sale with recorded payments cannot be cancelled.

### Invoices and payments

- `amount_paid + balance_due = total`
- `amount_paid` equals the sum of completed payments.
- Open invoice statuses are `unpaid`, `partially_paid`, and `overdue`.
- A payment must be positive and cannot exceed `balance_due`.
- Recording a payment updates the invoice, the customer's outstanding balance,
  and the related sale status atomically.

### Purchase orders

- `total = sum(line_total)`, `line_total = quantity * unit_cost`
- Valid transitions:
  - `draft -> pending_approval | cancelled`
  - `pending_approval -> approved | rejected | cancelled`
  - `approved -> ordered | cancelled`
  - `ordered -> partially_received | received | cancelled`
  - `partially_received -> received | cancelled`
- Receiving increases stock and writes `purchase_receipt` movements. Only
  `approved`, `ordered`, or `partially_received` orders can be received.

### Returns

- A return quantity cannot exceed the unreturned quantity on the sale.
- `refund_amount` defaults to `quantity * sale unit_price`.
- Approving a return restocks the sale warehouse, writes a `sales_return`
  movement, records the refund, and marks the return `processed`.
- Rejecting a return writes no stock movement and zeroes the refund.

### Accounting

- Accounts have a type, normal balance, and optional parent.
- Posted journal entries must balance exactly; drafts may exist but the seed data
  keeps them balanced too.
- Expenses post to `Expense` accounts.
- The financial summary is simplified: receivables from open invoices, payables
  from supplier balances, inventory at cost, revenue from invoiced sales, and
  approved/paid expenses.

## Tools

Fifty-four tools are registered. Read-only tools execute immediately; the
following are sensitive and pass through the approval node:

| Tool | Why it needs approval |
| --- | --- |
| `update_product` | Changes prices and master data |
| `deactivate_product` | Soft-deletes a product |
| `update_customer` | Changes credit limits and contact data |
| `adjust_stock` | Changes on-hand quantity |
| `transfer_stock` | Moves inventory between warehouses |
| `create_sale` | Creates a commercial document |
| `update_sale` | Confirms or cancels a sale |
| `cancel_sale` | Restores stock and voids documents |
| `create_invoice` | Creates a receivable |
| `record_payment` | Moves money and balances |
| `create_purchase_order` | Commits procurement |
| `update_purchase_order` | Approves/orders/cancels a PO |
| `receive_purchase_order` | Increases stock from a PO |
| `create_expense` | Creates a payable expense |
| `process_return` | Approves refunds and restocks goods |

Read-only examples: `list_products`, `get_product`, `search_products`,
`get_stock`, `check_low_stock`, `check_product_availability`,
`get_stock_movements`, `list_customers`, `get_customer`, `list_suppliers`,
`get_supplier`, `list_sales`, `get_sale`, `list_invoices`, `get_invoice`,
`get_outstanding_invoices`, `get_customer_balance`, `list_purchase_orders`,
`get_purchase_order`, `list_accounts`, `get_account`, `list_expenses`,
`get_financial_summary`, `get_sales_summary`, `create_return_request`,
`get_return`, `list_returns`, `get_pending_approvals`,
`get_approval_details`, `get_approval_history`.

## Validation

`validate_dataset()` checks:

- required metadata and collections
- unique primary IDs and SKUs
- foreign keys for products, stock, movements, sales, invoices, payments, POs,
  accounts, journal lines, returns, approvals, and audit actors
- category and manager cycles
- sales line/total arithmetic, invoice balance identities, payment sums, PO
  totals, posted-journal balance, customer outstanding balances
- reserved <= on-hand and non-negative availability
- approval resources exist in the matching collection

The validator never repairs data. A failed validation raises
`DatasetValidationError` and aborts the write, leaving the previous file intact.

## Reviewer identity and log retention

- `INVENTORY_OPERATOR_ID` (default `EMP-006`) maps the person at the CLI to an
  employee for `audit_log.actor_id` and `new_value.reviewed_by`. An unknown ID
  falls back to `HUMAN_OPERATOR` and logs a warning at startup.
- `INVENTORY_OPERATION_LOG_LIMIT` (default 500) keeps the newest operation-log
  entries used for idempotency.
- `INVENTORY_AUDIT_LOG_LIMIT` (default 1000) keeps the newest audit entries.
- Old entries are dropped, not archived to a second file. The operation ledger
  keeps the latest entry, so in-flight idempotency checks remain valid.
- `/approvals` is a read-only CLI command that lists the live graph interrupt for
  the current thread and the seeded pending business approvals. It does not
  approve anything.

## Persistence limitations

- One JSON document, one process writer. A `threading.RLock` serialises writes
  inside the process; it is not a cross-process lock.
- Reads use an in-memory snapshot; mutations reload from disk before changing
  anything, so lost updates are avoided within one process.
- The dataset is intentionally small. It is not a substitute for a relational
  database, transactions across tables, or concurrent multi-user access.
- `operation_log` provides idempotency for sensitive operations. It is part of
  the same atomic write as the business mutation, so a crash before the write
  leaves neither behind, and a crash after it leaves both.
