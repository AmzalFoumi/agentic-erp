"""Stock movements and adjustment history. NOT YET IMPLEMENTED.

The distinction between this module and `products.py` is worth stating, because
the boundary is not obvious:

  products.py   the *catalogue*, plus the current stock level as a single
                number (`quantity_on_hand`).
  inventory.py  the *ledger* - one row per movement, with a reason, a
                timestamp and an actor. "Why is there only one left?" is a
                question only a ledger can answer.

`products.adjust_stock` currently writes the new total and forgets how it got
there. When this module lands, that function delegates here, and
`quantity_on_hand` becomes a cached sum of the movement rows rather than the
source of truth.

TODO (after slice 1 is proven end to end):
  - core/models.py: a StockMovement model (product_id, delta, reason, actor, at)
  - record_movement(session, actor, *, product_id, delta, reason)
  - list_movements(session, actor, *, product_id, limit, offset)
  - recalculate_on_hand(session, actor, *, product_id)
"""
