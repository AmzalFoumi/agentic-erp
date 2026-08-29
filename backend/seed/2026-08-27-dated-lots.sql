-- Give the perishable products realistic delivery batches with expiry dates.
--
-- WHY THIS EXISTS
-- The migration that created `inventory_lots` gave every product with stock one
-- lot holding the current quantity and NO expiry date - the honest state for
-- stock that was on the shelf before the shop tracked expiry. The spoilage scan
-- skips undated lots, so immediately after the migration the feature correctly
-- reports nothing at all.
--
-- That is right, and it is also unshowable. This script splits part of each
-- perishable's opening stock into dated batches, so the shop looks like a shop
-- that has been receiving deliveries.
--
-- WHY IT SPLITS RATHER THAN DELETES
-- The plan originally said "delete the catalogue and reseed it with expiry
-- dates". Splitting is strictly better now that lots exist: product ids survive
-- (so nothing pointing at them breaks), and **every product's total is
-- unchanged**, because each dated lot is carved out of the same product's
-- OPENING lot. Nothing is destroyed, so nothing has to be restored.
--
-- The "before" snapshot is still `2026-08-27-products-snapshot.sql`.
--
-- ⚠️ DATES ARE RELATIVE TO CURRENT_DATE, NEVER LITERAL.
-- A fixed date like '2026-08-29' is correct on the day it is written and wrong
-- every day after - by the demo it would be a shop full of stock that expired
-- last week. `CURRENT_DATE + 1` means "tomorrow" whenever this is run.
--
-- IDEMPOTENT: re-running changes nothing. Every insert is guarded on the lot
-- code not already existing for that product, and the OPENING lot is only
-- reduced when the matching batch is actually created.
--
-- HOW TO RUN
--   psql "$DATABASE_URL" -f backend/seed/2026-08-27-dated-lots.sql
-- or paste it into the Supabase SQL editor.

BEGIN;

-- One row per batch we want to exist. `days` is the offset from today, so the
-- data ages correctly no matter when this runs; NULL would mean undated, which
-- this script never creates.
--
-- The spread is deliberate and covers every branch of the discount ladder:
--   day 0  -> 70% off   (expires today)
--   day 1  -> 50% off   (tomorrow)
--   day 2  -> 25% off   (in two days)
--   day 9  -> no tier   (proves the horizon actually excludes things)
WITH wanted (sku, lot_code, days, qty) AS (
    VALUES
        -- Expiring TODAY. The most urgent rung, and the one a manager most
        -- wants to see before the shop closes.
        ('1234-2345', 'DN-BREAD-A',  0, 40),   -- Sourdough
        ('2004-1001', 'DN-FRUIT-A',  0, 24),   -- Bananas
        ('2002-1002', 'DN-DAIRY-A',  0, 36),   -- Set Yoghurt

        -- Expiring TOMORROW.
        ('1234-2345', 'DN-BREAD-B',  1, 60),   -- Sourdough
        ('2002-1001', 'DN-DAIRY-B',  1,  6),   -- Full Cream Milk
        ('2003-1002', 'DN-MEAT-A',   1,  6),   -- Chicken Breast
        ('2005-1000', 'DN-DAIRY-C',  1, 30),   -- Mozzarella
        ('2004-1002', 'DN-VEG-A',    1, 10),   -- Tomatoes

        -- Expiring in TWO days.
        ('2002-1003', 'DN-DAIRY-D',  2,  3),   -- Cheddar
        ('2003-1001', 'DN-EGG-A',    2, 12),   -- Eggs
        ('2004-1004', 'DN-VEG-B',    2, 15),   -- Carrots
        ('2002-1820', 'DN-ALT-A',    2, 40),   -- Oat Milk

        -- Comfortably in the future. These must NOT appear in the spoilage
        -- report; if they ever do, the horizon has broken.
        ('2002-1004', 'DN-DAIRY-E',  9, 10),   -- Butter
        ('2004-1004', 'DN-VEG-C',   14, 20)    -- Carrots
),
resolved AS (
    SELECT p.id AS product_id, p.cost_price, p.sell_price,
           w.lot_code, w.days, w.qty
    FROM wanted w
    JOIN products p ON p.sku = w.sku
    -- Only carve out batches the product can actually spare.
    --
    -- ⚠️ The check is against the product's TOTAL request, not this one row.
    -- Two products here ask for more than one batch - Sourdough wants 100
    -- units across two, Carrots 35 across two - and checking each row against
    -- the same OPENING lot would let both pass independently when the lot can
    -- cover either alone but not both. The later UPDATE would then drive
    -- OPENING negative.
    WHERE EXISTS (
        SELECT 1
        FROM inventory_lots o
        WHERE o.product_id = p.id
          AND o.lot_code = 'OPENING'
          AND o.quantity >= (
              SELECT SUM(w2.qty) FROM wanted w2 WHERE w2.sku = w.sku
          )
    )
    -- Skip anything already created by a previous run.
    AND NOT EXISTS (
        SELECT 1 FROM inventory_lots l
        WHERE l.product_id = p.id AND l.lot_code = w.lot_code
    )
),
inserted AS (
    INSERT INTO inventory_lots (
        product_id, lot_code, expiry_date, quantity, cost_price, sell_price,
        created_by, created_via
    )
    -- `sell_price` copied from the product's catalogue price, exactly as the
    -- migration backfilled the OPENING lots and as `receive_lot` does for a
    -- real delivery. `discount_percent` takes its column default of 0.
    SELECT product_id, lot_code, CURRENT_DATE + days, qty, cost_price, sell_price,
           'seed', 'system'
    FROM resolved
    RETURNING product_id, quantity
)
-- Take the same quantity back off the OPENING lot, so the product's total is
-- exactly what it was before this script ran.
UPDATE inventory_lots o
SET quantity = o.quantity - t.moved,
    updated_by = 'seed'
FROM (
    SELECT product_id, SUM(quantity) AS moved
    FROM inserted
    GROUP BY product_id
) t
WHERE o.product_id = t.product_id AND o.lot_code = 'OPENING';

-- Belt and braces: recompute every product's summary from its lots. This
-- should change nothing, because the arithmetic above is conservative - but
-- `quantity_on_hand` is a cached total, and a seed script is exactly the kind
-- of place a cached total silently stops matching.
UPDATE products p
SET quantity_on_hand = COALESCE(
    (
        SELECT SUM(l.quantity)
        FROM inventory_lots l
        WHERE l.product_id = p.id
    ),
    0
);

-- Same idea for the lot-price roll-ups (`services/lots.recalculate_price_stats`
-- is the runtime equivalent). Every seeded lot took its product's catalogue
-- price, so this leaves min = max = avg = the catalogue price - correct, and
-- it means the product screens do not show a stale range from before the seed.
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
--   -- no lot holds a negative quantity
--   SELECT * FROM inventory_lots WHERE quantity < 0;
