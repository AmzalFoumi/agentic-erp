"""Purchasing: who we buy from, what we order, and what to order today.

### This package's public surface is `__all__` below, and nothing else

Other code writes `from services import purchasing` and calls what is listed
here. `_repository` and every module internal are not part of the contract,
which is what lets the package be reorganised without touching a caller.

`__all__` is written out by hand rather than left implicit, so that adding a
function to one of the modules below does not silently widen what the rest of
the application may depend on.

### The modules

  quantities.py   pure arithmetic - how much to buy. No session, no clock
  _repository.py  every query. Private
  suppliers.py    supplier use cases
  catalog.py      which supplier stocks what, at what price
  reorder.py      the scan and the bundler
  orders.py       create / send / cancel - the state machine
  drafts.py       the SUPPLIER_REORDER draft type and its handler

### Why this one is a package when its neighbours are flat modules

It is the shape the rest of `services/` is intended to move to - see
docs/superpowers/specs/2026-08-27-gate29-purchasing-design.md, "Documented
follow-up". Gate 29 proves the shape on new code first, which is the cheap way
to find out whether it is right before applying it to code that already works.
"""

from services.purchasing.catalog import (
    link_product,
    list_supplier_products,
    update_link,
)
from services.purchasing.orders import (
    cancel_order,
    create_order,
    get_order,
    list_orders,
    send_order,
)
from services.purchasing.drafts import SUPPLIER_REORDER, propose_reorder
from services.purchasing.receiving import receive_order
from services.purchasing.reorder import (
    ReorderBundle,
    ReorderLine,
    ReorderReport,
    scan_reorder,
)
from services.purchasing.suppliers import (
    create_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
)

__all__ = [
    "SUPPLIER_REORDER",
    "ReorderBundle",
    "ReorderLine",
    "ReorderReport",
    "cancel_order",
    "create_order",
    "create_supplier",
    "get_order",
    "get_supplier",
    "link_product",
    "list_orders",
    "list_supplier_products",
    "list_suppliers",
    "propose_reorder",
    "receive_order",
    "scan_reorder",
    "send_order",
    "update_link",
    "update_supplier",
]
