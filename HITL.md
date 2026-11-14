# Human-in-the-Loop (HITL) implementation

This document describes how BAYAZID AI pauses before sensitive inventory actions,
how the human approves, edits, or rejects them, and how the paused run resumes
without duplicating business effects.

The same LangGraph graph and the same `SqliteSaver` checkpointer are used. There
is no separate HITL framework, no web UI, and no auto-approval tool.

## 1. Why approval is a graph concern

The model must never be able to perform a sensitive operation simply by calling a
tool. The gate has to sit between "the model asked for a tool" and "the tool
runs". In this project that gate is a LangGraph node:

```text
START -> chat_node
           │
           ├─ no tool calls ───────────────────────────────► END
           │
           ├─ only non-sensitive calls ──► tools ─────────► chat_node
           │
           └─ any sensitive call ────────► approval ──────► chat_node
                                             │
                                             └─ interrupt() waits for the human
```

`graph/workflow.py` keeps the original `ToolNode` path for non-sensitive tools.
When a tool name appears in `SENSITIVE_TOOLS`, the message is routed to the
`approval` node instead (see `graph/approval.py`).

## 2. Sensitive tools

The inventory package declares the policy in
`src/agentic_chatbot/inventory/approvals.py`:

```python
SENSITIVE_TOOLS = {
    "update_product": "Update Product",
    "deactivate_product": "Deactivate Product",
    "update_customer": "Update Customer",
    "adjust_stock": "Adjust Stock",
    "transfer_stock": "Transfer Stock",
    "create_sale": "Create Sale",
    "update_sale": "Update Sale",
    "cancel_sale": "Cancel Sale",
    "create_invoice": "Create Invoice",
    "record_payment": "Record Payment",
    "create_purchase_order": "Create Purchase Order",
    "update_purchase_order": "Update Purchase Order",
    "receive_purchase_order": "Receive Purchase Order",
    "create_expense": "Create Expense",
    "process_return": "Approve / Process Return",
}
```

Read-only tools (`list_products`, `check_low_stock`, `get_outstanding_invoices`,
`get_customer_balance`, ...) are never interrupted. A list or lookup should not
require permission.

## 3. The interrupt payload

When the approval node reaches a sensitive call it builds a payload and calls
LangGraph's `interrupt()`:

```json
{
  "kind": "approval_request",
  "tool": "update_product",
  "title": "Update Product",
  "tool_call_id": "call-abc",
  "operation_id": "thread-1:call-abc",
  "arguments": {"product_id": "PRD-1001", "selling_price": 95000},
  "details": [
    ["Product", "Latitude Business Laptop 14"],
    ["SKU", "LAP-BIZ-14-001"],
    ["Current Selling Price", "BDT 89,500"],
    ["Proposed Selling Price", "BDT 95,000"]
  ],
  "warnings": [],
  "approval_token": "sha256(...)",
  "requested_by": "AI Agent",
  "reason": "The agent requested a sensitive inventory operation."
}
```

`details` comes from `InventoryService.preview_operation()`, a **read-only**
method. It is how the panel can show the current and proposed price without
executing anything. The graph layer receives the preview function as a callback,
so it stays independent of the inventory package.

## 4. Decision types

The human returns one of three decisions:

| Decision | Resume payload | Effect |
| --- | --- | --- |
| Approve | `{"action": "approve", "approval_token": ..., "comment": ...}` | Executes the tool with the original arguments |
| Edit | `{"action": "edit", "arguments": {...}, "approval_token": ..., "comment": ...}` | Opens the field editor, then executes the confirmed arguments |
| Reject | `{"action": "reject", "approval_token": ..., "comment": ...}` | Executes nothing and returns a rejection ToolMessage to the model |

`respond` (free-text clarification) is intentionally not an approval. There is no
tool that grants approval, so the agent cannot approve its own proposal. The only
path that produces a resume value is the CLI's human interaction.

### Field-level editing

`Edit` does not ask for raw JSON. The approval node adds two pieces of metadata
to the payload:

- `editable_fields` — every argument accepted by the tool schema, so a reviewer
  can also add an optional field that the model omitted.
- `field_types` — the primitive type of each field (`string`, `integer`,
  `number`, `boolean`, `array`, `object`), extracted from the tool schema,
  including `Optional` unions.

The CLI's editor lists the fields with their current values. The reviewer picks a
number or an exact name, types a value, and repeats. Values are coerced to the
declared type; invalid input is reported and the editor stays open. `c` cancels
the edit and returns to the decision menu; a blank field selection finishes the
edit and shows only the changed values for confirmation. Complex values (lists
and objects) are entered as JSON at the field prompt.

```text
Editable arguments
  1. product_id = 'PRD-1001'
  2. name = 'Latitude Business Laptop 14 Pro'
  3. category_id = <not set>
  ...
Field to edit (number/name, 'c' to cancel, blank to finish): 2
name [Latitude Business Laptop 14 Pro]: Latitude Business Laptop 14 Supreme
...
Proposed argument changes
  name: 'Latitude Business Laptop 14 Pro' -> 'Latitude Business Laptop 14 Supreme'
Execute with these arguments? (y/n):
```

### Binding an approval to a proposal

`approval_token = sha256(tool + canonical arguments + tool_call_id)`. On resume,
the node recomputes the token and compares it with the decision. A mismatch means
the decision belongs to a different proposal; the node refuses to execute and
returns:

```text
Error: this approval does not match the current proposal.
The action was not executed; request a fresh approval.
```

This is why an edited proposal still requires a human decision: the CLI edits the
arguments **as part of** that decision, and the graph executes exactly those
arguments. A stale token from an earlier proposal cannot be replayed.

## 5. Resume flow

1. The graph streams until `interrupt()`; LangGraph writes a checkpoint and stops.
2. `ChatService._events_from_chunk()` turns the `__interrupt__` update into a
   `TurnEvent(type="interrupt", payload=...)`.
3. `cli/chat.py` renders the panel and collects the decision.
4. `ChatService.resume_turn(thread_id, decision)` calls
   `graph.stream(Command(resume=decision), config={"configurable": {"thread_id":
   thread_id}})`.
5. The approval node re-executes, `interrupt()` returns the decision, and the node
   either invokes the tool or returns a rejection `ToolMessage`.
6. The graph continues to `chat_node`, which produces the final answer.

Because the checkpoint lives in SQLite (`chatbot_memory.db`), the pending
approval survives a process restart. On startup `cli/app.py` calls
`ChatService.get_pending_interrupt(thread_id)` and offers the same panel before
the input loop. The same thread ID resumes the same execution.

## 6. Exactly-once behaviour

A checkpoint alone cannot promise exactly-once execution: the process could crash
after the business write but before LangGraph records the ToolMessage.

The project adds a lightweight operation ledger:

- `operation_id = f"{thread_id}:{tool_call_id}"`.
- The approval node injects it through `RunnableConfig`
  (`configurable["inventory_operation_id"]`).
- Each sensitive service method accepts `operation_id` and runs inside one
  `InventoryStore.transaction()`:
  1. if the operation ID is already recorded, return the stored result;
  2. otherwise perform the mutation and append the operation record;
  3. validate the whole dataset;
  4. atomically replace the JSON file.

The mutation and the ledger entry therefore commit together. Re-invoking the same
approved operation returns the cached result instead of applying it twice.

## 7. CLI experience

```text
╭────────────────────── HUMAN APPROVAL REQUIRED ───────────────────────╮
│ Action: Update Product                                               │
│                                                                      │
│ Product: Latitude Business Laptop 14                                 │
│ SKU: LAP-BIZ-14-001                                                  │
│ Current Selling Price: BDT 89,500                                    │
│ Proposed Selling Price: BDT 95,000                                   │
│                                                                      │
│ Requested By: AI Agent                                               │
│ Reason: The agent requested a sensitive inventory operation.         │
│ Reviewer: Shirin Sultana (EMP-006)                                   │
│                                                                      │
│ [A] Approve    [E] Edit Arguments    [R] Reject                      │
╰──────────────────────────────────────────────────────────────────────╯
Decision [A]pprove / [E]dit / [R]eject:
```

Every prompt terminates its own line, and a decision prints
`Approval recorded. Continuing…` before the resumed tool result. If the reviewer
cancels, the CLI prints `Returning to chat. Use /approvals to inspect pending
actions.` The main framed prompt is restored in both cases, so the approval
screen can never trap the session.

Approval questions use a separate plain console prompt rather than the framed
composer. That keeps the main `PromptSession` untouched, so the composer returns
immediately after the decision. `/approve`, `/edit`, and `/reject` are accepted
as well as `A`, `E`, and `R`.

`/approvals` is a read-only command that lists the live interrupt for the current
thread (action, operation ID, arguments) and the seeded pending business
approvals. It does not decide anything; the decision panel appears the next time
the thread continues. It shows the configured reviewer identity as well.

The CLI never claims success before the tool result arrives. A rejection is
reported to the model as a tool result, so the final answer can say plainly that
nothing changed. When the reviewer edits arguments, the tool result contains the
executed values and the prompt tells the model to report those values rather than
its original proposal.

### Reviewer identity and log retention

`INVENTORY_OPERATOR_ID` (default `EMP-006`, Shirin Sultana, Finance Controller)
is the employee recorded as the reviewer in `audit_log.actor_id` and in
`new_value.reviewed_by`. The approval panel shows the same reviewer label. If the
configured ID is not an employee, the service falls back to `HUMAN_OPERATOR` and
logs a warning at startup.

`INVENTORY_OPERATION_LOG_LIMIT` (default 500) and
`INVENTORY_AUDIT_LOG_LIMIT` (default 1000) cap the two logs. Appends keep the
newest N entries; older entries are dropped. The operation ledger is trimmed only
after a sensitive mutation commits, and the newest entry is always retained, so
in-flight idempotency checks are unaffected.

## 8. Worked scenarios

### Delete a product

```text
User: Delete product PRD-1005.
Agent: get_product -> deactivate_product(product_id="PRD-1005", reason=...)
Graph: interrupt before the update
Human: approve | edit reason/target | reject
```

`deactivate_product` is a soft delete. Sales, purchase orders, and stock
movements keep their historical references. There is no hard-delete tool.

### Increase a price

```text
User: Increase the selling price of PRD-1001 to 95000.
Agent: get_product -> update_product(selling_price=95000)
Panel: current 89,500 -> proposed 95,000
Human: approve, edit the value, or reject
```

An edited value is executed after confirmation and recorded in `audit_log` as
`approval_edited`.

### Reduce stock

```text
User: Reduce the stock of PRD-1001 by 3 units.
Agent: check_product_availability -> adjust_stock(quantity_change=-3, reason=...)
```

The service rejects a zero change and any change that would make on-hand or
available negative. The movement and the stock row update in one transaction.

### Create a purchase order

```text
User: Create a purchase order for 10 routers from SUP-003.
Agent: get_supplier -> search_products("router") -> create_purchase_order(...)
```

The order is created as `pending_approval`. Only after approval can it move to
`approved`, then `ordered`, then be received into stock.

### Record a payment

```text
User: Record a payment of BDT 20000 against invoice INV-2026-001.
Agent: get_invoice -> record_payment(amount=20000, method=...)
```

The service checks the invoice status, validates `amount <= balance_due`, and on
approval updates the invoice, customer balance, and sale status together.

### Approve a return

```text
User: Approve return RET-2026-001.
Agent: get_return -> process_return(decision="approve")
```

On approval the return is restocked, a `sales_return` movement is written, the
refund is recorded, and the return becomes `processed`.

## 9. Testing

Automated coverage lives in:

| File | Scope |
| --- | --- |
| `tests/test_hitl.py` | interrupt, approve, reject, edit, stale token, multiple approvals, discount approval, stock adjustment (approve/edit/reject), restart, duplicate resume, ChatService events |
| `tests/test_cli_approval.py` | panel rendering, A/E/R decisions, field-level editing and type coercion, invalid values, edit cancellation, no resume on cancel, startup resume |
| `tests/test_cli_commands.py` | `/approvals` read-only listing of live interrupts and seeded approvals |
| `tests/test_inventory_dataset.py` | JSON loading, validation failures, atomic writes, locking |
| `tests/test_inventory_service.py` | business workflows, idempotency, operator mapping, log retention |
| `tests/test_inventory_tools.py` | tool registration, descriptions, sensitive set, direct execution |

Run them with:

```bash
uv run pytest tests/test_hitl.py tests/test_cli_approval.py tests/test_cli_commands.py -v
```

Manual CLI checks:

```text
Increase the selling price of PRD-1001 to 95000.
Change the name of product PRD-1001 to Latitude Business Laptop 14 Supreme.  # choose E, edit field 2
Delete product PRD-1005.
Reduce the stock of PRD-1001 by 3 units.
Create a purchase order for 10 routers from SUP-003.
Record a payment of BDT 20000 against invoice INV-2026-001.
Approve return RET-2026-001.
/approvals
```

To test a restart, trigger an approval, quit with `Ctrl+D` while the panel is
waiting, and start the CLI again. The panel reappears for the restored thread.

## 10. Limitations

- Human identity is not authenticated. `INVENTORY_OPERATOR_ID` maps the reviewer
  to an employee in the audit trail, but it is a configured identity, not a login;
  anyone at the CLI is treated as that employee. If the ID is unknown, the log
  falls back to `HUMAN_OPERATOR`.
- The approval token detects stale or mismatched proposals; it is not a
  cryptographic signature and does not protect against someone editing the
  checkpoint database directly.
- The JSON store is single-writer. The lock is per process, not cross-process.
- The audit write is a separate transaction from the tool execution. If it fails,
  the operation has still happened and the failure is logged.
- `operation_log` and `audit_log` are capped by retention settings; older entries
  are dropped, not archived to a second file.
- `interrupt()` pauses the graph, not the process. A pending approval is safe on
  disk, but a second process must not write the same JSON dataset concurrently.
- `get_pending_approvals()` reports seeded dataset approvals; live graph
  interrupts are approved through the CLI panel, and `/approvals` only lists them.
