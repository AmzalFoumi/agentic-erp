"""Purchase orders - restocking. NOT YET IMPLEMENTED.

This is where the system stops being a database with a UI and starts being
useful: given `reorder_level` on every product and `lead_time_days` on every
supplier, it can propose what to buy today, and receiving a delivery becomes
one call that moves stock for every line at once.

It is also the first module with a real state machine (draft -> sent ->
partially received -> received / cancelled), which is exactly the kind of rule
that must live in `services/` - an adapter cannot be trusted to enforce a legal
transition, because there will be two adapters and they will drift.

TODO (after slice 1 is proven end to end):
  - core/models.py: PurchaseOrder + PurchaseOrderLine models
  - suggest_reorder(session, actor)          # products at or below reorder_level
  - create_order / send_order / receive_order(session, actor, ...)
    where receiving delegates stock changes to inventory.record_movement
"""
