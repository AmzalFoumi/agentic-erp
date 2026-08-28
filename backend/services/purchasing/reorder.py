"""What to buy today, grouped by supplier and topped up to their minimum.

### The problem, in one sentence

The system already knows which products are low - `Product.needs_reorder` is a
hybrid_property that compiles to SQL. What it cannot do without this module is
turn that list into orders, because you do not buy from "the shop": you buy
from named suppliers, most of whom refuse to ship below a minimum order value.

### The rule, in four steps

  1. For each low product, choose one supplier: preferred, then cheapest, then
     lowest id. The third looks pointless and is not - see `_choose_supplier`.
  2. Order up to twice the reorder level, rounded up to whole packs.
     (`quantities.order_quantity`.)
  3. Group by supplier and price the group.
  4. If the group is under that supplier's minimum, add their other products -
     the ones closest to going low - a pack at a time until it clears. If it
     still cannot, say so rather than proposing it silently.

### What this module does not do

It writes nothing. `scan_reorder` is a query that returns frozen dataclasses.
Staging a bundle as an Action Draft is `drafts.py`; creating the actual order
is `orders.py`, and only after a human approves.

### The caveat, recorded rather than hidden

It reads `quantity_on_hand` and does not look at expiry. A bundle can therefore
propose reordering a product that also appears on the spoilage report. That is
technically consistent - you are low AND what you have is about to expire is
exactly when you reorder - but it reads oddly on screen. Not solved here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from core.actor import Actor
from core.models import Product, Supplier, SupplierProduct
from services import pricing
from services.guards import require_permission
from services.purchasing import _repository as repo
from services.purchasing import quantities

# How many top-up passes before giving up. A guard against a pathological
# configuration (a supplier whose every product has pack_size 1 and unit_cost
# 0.00 can never raise the total) turning into an infinite loop.
_MAX_TOP_UP_STEPS = 500


@dataclass(frozen=True)
class ReorderLine:
    """One product on one proposed order.

    `is_top_up` is the honest label: False means "this is low and we are
    replacing it", True means "this is not low yet, and it is here because the
    order needed to reach the supplier's minimum". A manager reading the
    proposal is entitled to know which is which.
    """

    product_id: int
    sku: str
    name: str
    quantity_on_hand: int
    reorder_level: int
    quantity: int
    unit_cost: Decimal
    pack_size: int
    line_total: Decimal
    is_top_up: bool


@dataclass(frozen=True)
class ReorderBundle:
    """One supplier's proposed order."""

    supplier_id: int
    supplier_name: str
    lead_time_days: int
    minimum_order_value: Decimal
    bundle_value: Decimal
    below_minimum: bool
    shortfall: Decimal
    lines: tuple[ReorderLine, ...]


@dataclass(frozen=True)
class ReorderReport:
    """Everything worth buying today.

    `unsourced` holds low products no active supplier stocks. They are reported
    rather than dropped: "we cannot buy this from anyone" is a thing the
    manager needs to know, and a silently shorter list looks like the feature
    working.
    """

    bundles: tuple[ReorderBundle, ...]
    unsourced: tuple[dict, ...]
    total_value: Decimal


def _choose_supplier(offers: list[SupplierProduct]) -> SupplierProduct | None:
    """Pick one offer for a product from the offers available.

    Order: preferred first, then cheapest, then lowest supplier id.

    ⚠️ **The third tiebreak looks pointless and is load-bearing.** The same
    scan run twice must produce the same bundle. Without a total order, two
    suppliers at the same price could swap places between two reads, and the
    approval screen would contradict itself between refreshes - with real
    money on it.
    """
    if not offers:
        return None
    return min(
        offers,
        key=lambda offer: (
            not offer.is_preferred,
            offer.unit_cost,
            offer.supplier_id,
        ),
    )


def _line_for(
    product: Product, offer: SupplierProduct, quantity: int, *, is_top_up: bool
) -> ReorderLine:
    return ReorderLine(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        quantity_on_hand=product.quantity_on_hand,
        reorder_level=product.reorder_level,
        quantity=quantity,
        unit_cost=offer.unit_cost,
        pack_size=offer.pack_size,
        line_total=pricing.to_money(Decimal(quantity) * offer.unit_cost),
        is_top_up=is_top_up,
    )


def _headroom(product: Product) -> int:
    """How far a product is from needing reordering. Smaller is more urgent."""
    return product.quantity_on_hand - product.reorder_level


def _top_up(
    session: Session,
    supplier: Supplier,
    chosen: dict[int, ReorderLine],
    current_value: Decimal,
) -> tuple[dict[int, ReorderLine], Decimal]:
    """Add packs of this supplier's other products until the minimum clears.

    Candidates are that supplier's products which are NOT already on the order,
    ranked by headroom (closest to going low first), then by cost, then by id
    for determinism.

    One pack is added per step, re-checking the total each time, so the order
    overshoots the minimum by at most one pack of the cheapest useful thing.
    Adding a whole line at once would clear the minimum by a wide and arbitrary
    margin.
    """
    links = repo.links_for_supplier(session, supplier.id)
    candidate_ids = [link.product_id for link in links if link.product_id not in chosen]
    products = repo.products_by_id(session, candidate_ids)

    candidates = sorted(
        (link for link in links if link.product_id in products),
        key=lambda link: (
            _headroom(products[link.product_id]),
            link.unit_cost,
            link.product_id,
        ),
    )

    steps = 0
    for link in candidates:
        product = products[link.product_id]
        while current_value < supplier.minimum_order_value:
            steps += 1
            if steps > _MAX_TOP_UP_STEPS:
                return chosen, current_value

            existing = chosen.get(product.id)
            quantity = (existing.quantity if existing else 0) + link.pack_size
            chosen[product.id] = _line_for(product, link, quantity, is_top_up=True)

            current_value = quantities.bundle_value(
                [(line.quantity, line.unit_cost) for line in chosen.values()]
            )

            # A free product cannot raise the total, so move to the next
            # candidate rather than adding it forever.
            if link.unit_cost <= 0:
                break

        if current_value >= supplier.minimum_order_value:
            break

    return chosen, current_value


def scan_reorder(session: Session, actor: Actor) -> ReorderReport:
    """What to buy today. **Reads only** - nothing is written or proposed."""
    require_permission(actor, "purchasing.read")

    low = repo.low_products(session)
    offers = repo.links_for_products(session, [product.id for product in low])

    by_product: dict[int, list[SupplierProduct]] = {}
    for offer in offers:
        by_product.setdefault(offer.product_id, []).append(offer)

    # supplier_id -> {product_id -> line}
    grouped: dict[int, dict[int, ReorderLine]] = {}
    unsourced: list[dict] = []

    for product in low:
        offer = _choose_supplier(by_product.get(product.id, []))
        if offer is None:
            unsourced.append(
                {
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "quantity_on_hand": product.quantity_on_hand,
                    "reorder_level": product.reorder_level,
                }
            )
            continue

        quantity = quantities.order_quantity(
            quantity_on_hand=product.quantity_on_hand,
            reorder_level=product.reorder_level,
            pack_size=offer.pack_size,
        )
        if quantity <= 0:
            continue

        grouped.setdefault(offer.supplier_id, {})[product.id] = _line_for(
            product, offer, quantity, is_top_up=False
        )

    bundles: list[ReorderBundle] = []
    for supplier_id in sorted(grouped):
        supplier = repo.get_supplier(session, supplier_id)
        if supplier is None:  # pragma: no cover - the FK makes this unreachable
            continue

        chosen = grouped[supplier_id]
        value = quantities.bundle_value(
            [(line.quantity, line.unit_cost) for line in chosen.values()]
        )

        if value < supplier.minimum_order_value:
            chosen, value = _top_up(session, supplier, chosen, value)

        shortfall = supplier.minimum_order_value - value
        below = shortfall > 0

        bundles.append(
            ReorderBundle(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                lead_time_days=supplier.lead_time_days,
                minimum_order_value=supplier.minimum_order_value,
                bundle_value=value,
                below_minimum=below,
                shortfall=pricing.to_money(shortfall) if below else Decimal("0.00"),
                # Sorted so two scans list the lines in the same order.
                lines=tuple(
                    sorted(chosen.values(), key=lambda line: line.product_id)
                ),
            )
        )

    return ReorderReport(
        bundles=tuple(bundles),
        unsourced=tuple(unsourced),
        total_value=pricing.to_money(
            sum((bundle.bundle_value for bundle in bundles), Decimal("0"))
        ),
    )
