-- More dated delivery batches for the perishable catalogue.
--
-- WHY THIS EXISTS
-- `2026-08-27-dated-lots.sql` gave each perishable one or two dated batches,
-- enough to demo the spoilage scan. This file widens that: more products, a
-- longer spread of future dates, and - new here - a couple of batches that are
-- ALREADY PAST their expiry date, so the "expired stock is a write-off, not a
-- discount" behaviour (2026-09-10) has something to show.
--
-- HOW IT DIFFERS FROM THE 2026-08-27 FILE
-- That one SPLITS each batch out of the product's undated OPENING lot, so
-- totals never move. This one is ADDITIVE: every row is a new delivery and the
-- product's quantity_on_hand goes UP by that amount. That is the honest model
-- for "the shop received more stock", it needs no OPENING lot to draw from,
-- and it cannot drive any lot negative.
--
-- ⚠️ DATES ARE RELATIVE TO CURRENT_DATE, NEVER LITERAL.
-- `CURRENT_DATE + days` where `days` may be negative. A fixed date would be
-- correct the day it was written and wrong every day after.
--
-- IDEMPOTENT: every insert is guarded on (product_id, lot_code) not already
-- existing, so re-running changes nothing.
--
-- Run it AFTER migration `a7f3c1e94b28` (lot pricing columns), the same as the
-- 2026-08-27 file.
--
-- HOW TO RUN
--   psql "$DATABASE_URL" -f backend/seed/2026-09-10-more-dated-lots.sql
-- or paste it into the Supabase SQL editor.

BEGIN;

-- One row per delivery batch. `days` is the offset from today; negative means
-- the batch is already expired and will be proposed as a write-off by the
-- spoilage scan. Lot codes are prefixed `MD-0910-` so they never collide with
-- the `DN-*` / `OPENING` lots already in the table.
WITH wanted (sku, lot_code, days, qty) AS (
    VALUES
        -- Already EXPIRED - these demonstrate the write-off path (price 0.00,
        -- 100% off, taken off sale on approval).
        ('2004-1001', 'MD-0910-BAN-X', -6, 12),   -- Bananas Ambul 1kg
        ('2002-1002', 'MD-0910-YOG-X', -3, 18),   -- Set Yoghurt 80g

        -- Near future - inside the markdown window (0-2 days is a discount rung).
        ('2003-1002', 'MD-0910-CHK-A',  2,  8),   -- Chicken Breast 1kg

        -- Comfortably in the future - NOT at risk, there so the shop looks
        -- stocked and the spoilage horizon has things to correctly exclude.
        ('2002-1001', 'MD-0910-MLK-A',  5, 24),   -- Full Cream Milk 1L
        ('2004-1002', 'MD-0910-TOM-A',  5, 14),   -- Tomatoes 1kg
        ('2005-1000', 'MD-0910-MOZ-A',  7, 20),   -- Mozzarella Cheese 250g
        ('1234-2345', 'MD-0910-BRD-A',  7, 30),   -- Sourdough 800g
        ('2002-1003', 'MD-0910-CHE-A', 12,  9),   -- Cheddar Cheese 200g
        ('2003-1001', 'MD-0910-EGG-A', 12, 24),   -- Chicken Eggs (10)
        ('2004-1004', 'MD-0910-CAR-A', 20, 40),   -- Carrots 1kg
        ('2002-1004', 'MD-0910-BUT-A', 45, 16),   -- Butter 227g
        ('2002-1820', 'MD-0910-OAT-A', 45, 36)    -- Oat Milk
),
resolved AS (
    SELECT p.id AS product_id, p.cost_price, p.sell_price,
           w.lot_code, w.days, w.qty
    FROM wanted w
    JOIN products p ON p.sku = w.sku
    -- Skip anything a previous run already created.
    WHERE NOT EXISTS (
        SELECT 1 FROM inventory_lots l
        WHERE l.product_id = p.id AND l.lot_code = w.lot_code
    )
)
INSERT INTO inventory_lots (
    product_id, lot_code, expiry_date, quantity, cost_price, sell_price,
    created_by, created_via
)
-- `sell_price` / `cost_price` copied from the product's catalogue figures,
-- exactly as `lots.receive_lot` does for a real delivery. `discount_percent`
-- takes its column default of 0.
SELECT product_id, lot_code, CURRENT_DATE + days, qty, cost_price, sell_price,
       'seed', 'system'
FROM resolved;

-- quantity_on_hand is a cached total the service layer maintains
-- (`services/lots.recalculate_on_hand`). We just changed the lots out from
-- under it, so recompute every product's from its rows.
UPDATE products p
SET quantity_on_hand = COALESCE(
    (
        SELECT SUM(l.quantity)
        FROM inventory_lots l
        WHERE l.product_id = p.id
    ),
    0
);

-- Same for the lot-price roll-ups (`services/lots.recalculate_price_stats`).
-- Every seeded lot took its product's catalogue price, so this leaves
-- min = max = avg = the catalogue price for the affected products.
UPDATE products p
SET min_cost_price = s.min_cost,
    max_cost_price = s.max_cost,
    avg_cost_price = round(s.avg_cost, 2),
    min_sell_price = s.min_sell,
    max_sell_price = s.max_sell,
    avg_sell_price = round(s.avg_sell, 2)
FROM (
    SELECT product_id,
           MIN(cost_price) AS min_cost, MAX(cost_price) AS max_cost,
           AVG(cost_price) AS avg_cost,
           MIN(sell_price) AS min_sell, MAX(sell_price) AS max_sell,
           AVG(sell_price) AS avg_sell
    FROM inventory_lots
    WHERE quantity > 0
    GROUP BY product_id
) s
WHERE p.id = s.product_id;

COMMIT;

-- Verification. Both should hold after a successful run:
--
--   -- no product's total disagrees with its lots
--   SELECT p.id FROM products p
--   LEFT JOIN inventory_lots l ON l.product_id = p.id
--   GROUP BY p.id, p.quantity_on_hand
--   HAVING p.quantity_on_hand <> COALESCE(SUM(l.quantity), 0);
--
--   -- the two expired batches are present and dated in the past
--   SELECT lot_code, expiry_date FROM inventory_lots
--   WHERE lot_code LIKE 'MD-0910-%X' AND expiry_date < CURRENT_DATE;
