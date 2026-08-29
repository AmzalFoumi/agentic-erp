"""lot-level sell price + discount, and product price roll-up columns

Revision ID: a7f3c1e94b28
Revises: 34334348fe8e
Create Date: 2026-08-29 12:00:00.000000

Hand-written, for the same backfill reason as the create-inventory-lots
migration: from the moment these columns exist the code reads them, so they
cannot arrive empty.

### What changes

A spoilage markdown used to rewrite `products.sell_price` - the price of every
carton of that product, including deliveries not yet on the shelf. It now
lowers the price of the one expiring **lot**. So:

  * `inventory_lots` gains `sell_price` (the shelf price for that batch) and
    `discount_percent` (how much a markdown took off; 0 = full price).
  * `products` gains six nullable roll-up columns - min / max / avg of the lot
    `cost_price` and lot `sell_price` across the product's lots that still have
    stock. NULL means "no lots with stock", and the screens fall back to the
    catalogue `products.sell_price` / `cost_price`.

### The backfill

Every existing lot's `sell_price` is set to its product's current
`sell_price` (the catalogue price), and `discount_percent` stays 0 - nothing
has been marked down yet under the new model. The product roll-ups are then
computed from those freshly-populated lots.

### Downgrade

Drops the eight columns. `products.sell_price` still holds the catalogue price
it always held, so the earlier state is consistent, not damaged. Any markdown
applied under the new model (which lives only on the lot) is lost on
downgrade - there is nowhere in the old schema to keep it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7f3c1e94b28"
down_revision: Union[str, Sequence[str], None] = "34334348fe8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- new lot columns -------------------------------------------------------
    #
    # A temporary server_default lets the ALTER fill existing rows in one pass;
    # it is dropped again at the end of this upgrade (see below), so new writers
    # must supply sell_price - the ORM does, and the seed script does.
    op.add_column(
        "inventory_lots",
        sa.Column(
            "sell_price",
            sa.Numeric(precision=10, scale=2),
            server_default="0.00",
            nullable=False,
        ),
    )
    # `discount_percent` keeps its server_default: 0 ("full price") is a
    # genuine, universal default, so raw INSERTs and the seed script can leave
    # it out. `sell_price` gets no lasting default - 0.00 would be a silent
    # mispricing, so every writer must supply it (the ORM does; the seed does).
    op.add_column(
        "inventory_lots",
        sa.Column(
            "discount_percent",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    # --- new product roll-up columns ----------------------------------------
    #
    # Nullable, no default: NULL is a real state ("no lots with stock").
    for col in (
        "min_cost_price",
        "max_cost_price",
        "avg_cost_price",
        "min_sell_price",
        "max_sell_price",
        "avg_sell_price",
    ):
        op.add_column(
            "products",
            sa.Column(col, sa.Numeric(precision=10, scale=2), nullable=True),
        )

    # --- backfill lot sell prices from the catalogue price -----------------
    op.execute(
        """
        UPDATE inventory_lots AS l
        SET sell_price = p.sell_price
        FROM products AS p
        WHERE p.id = l.product_id;
        """
    )

    # --- backfill product roll-ups from lots that have stock ---------------
    op.execute(
        """
        UPDATE products AS p
        SET min_cost_price = s.min_cost,
            max_cost_price = s.max_cost,
            avg_cost_price = round(s.avg_cost, 2),
            min_sell_price = s.min_sell,
            max_sell_price = s.max_sell,
            avg_sell_price = round(s.avg_sell, 2)
        FROM (
            SELECT product_id,
                   MIN(cost_price) AS min_cost,
                   MAX(cost_price) AS max_cost,
                   AVG(cost_price) AS avg_cost,
                   MIN(sell_price) AS min_sell,
                   MAX(sell_price) AS max_sell,
                   AVG(sell_price) AS avg_sell
            FROM inventory_lots
            WHERE quantity > 0
            GROUP BY product_id
        ) AS s
        WHERE p.id = s.product_id;
        """
    )

    # Drop only sell_price's temporary default now the existing rows are
    # filled - new inserts get its value from the ORM. discount_percent keeps
    # its default (see the note above).
    op.alter_column("inventory_lots", "sell_price", server_default=None)


def downgrade() -> None:
    op.drop_column("inventory_lots", "discount_percent")
    op.drop_column("inventory_lots", "sell_price")
    for col in (
        "avg_sell_price",
        "max_sell_price",
        "min_sell_price",
        "avg_cost_price",
        "max_cost_price",
        "min_cost_price",
    ):
        op.drop_column("products", col)
