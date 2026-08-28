-- Give the shop five suppliers with a price list, so the reorder bundler has
-- something to group and price against.
--
-- WHY THIS EXISTS
-- Gate 29 built the bundler, but it has nothing to bundle without suppliers
-- and supplier_products rows. Without this file, /purchasing/reorder-suggestions
-- correctly returns every low product as `unsourced` - the feature working, but
-- unshowable.
--
-- WHAT THIS DOES NOT DO
-- It does not touch products or inventory_lots. It only adds rows to the two
-- new tables this gate created: suppliers, supplier_products.
--
-- WHY THESE PARTICULAR CHOICES ARE LOAD-BEARING, NOT ARBITRARY
--   - Milk (2002-1001) and Cheddar (2002-1003) are each linked to TWO
--     suppliers at different prices, one marked preferred. Without a real
--     tie to break, _choose_supplier's "preferred wins even when dearer" rule
--     is never exercised by the demo data.
--   - Prime Meats & Poultry's minimum_order_value (60000) is set higher than
--     what its one low product (Chicken Breast) reaches alone, so its bundle
--     needs the top-up pass. A demo where every bundle clears its minimum on
--     the first pass never shows the branch that pass exists for.
--   - Pack sizes vary (1, 6, 12) across the links, so the "rounds up to whole
--     packs" rule is visible on more than one line.
--
-- IDEMPOTENT: every insert is guarded on the supplier name, or the
-- (supplier, product) pair, not already existing. Re-running changes nothing.
--
-- NO LITERAL DATES: there are none of the shop's own dates in this file -
-- lead_time_days is a duration, not a date, so there is nothing here that
-- ages the way 2026-08-27-dated-lots.sql's expiry dates do.
--
-- HOW TO RUN
--   psql "$DATABASE_URL" -f backend/seed/2026-08-27-suppliers.sql
-- or paste it into the Supabase SQL editor.

BEGIN;

-- --------------------------------------------------------------------------
-- Suppliers
-- --------------------------------------------------------------------------

INSERT INTO suppliers (name, contact_email, contact_phone, lead_time_days, minimum_order_value, is_active, created_by)
SELECT * FROM (VALUES
    ('Dairy Direct Ltd',        'orders@dairydirect.example',  '+94-11-555-0101', 2, 5000.00,  TRUE, 'seed'),
    ('Fresh Farms Produce',     'sales@freshfarms.example',     '+94-11-555-0102', 1, 8000.00,  TRUE, 'seed'),
    ('Golden Bakery Supplies',  'wholesale@goldenbakery.example','+94-11-555-0103', 3, 3000.00,  TRUE, 'seed'),
    -- Deliberately high: Prime Meats' one low product does not reach this
    -- alone, so its bundle exercises the top-up pass. See header.
    ('Prime Meats & Poultry',   'orders@primemeats.example',    '+94-11-555-0104', 4, 60000.00, TRUE, 'seed'),
    ('Value Wholesale Co',      'contact@valuewholesale.example','+94-11-555-0105', 7, 2000.00,  TRUE, 'seed')
) AS v(name, contact_email, contact_phone, lead_time_days, minimum_order_value, is_active, created_by)
WHERE NOT EXISTS (
    SELECT 1 FROM suppliers s WHERE s.name = v.name
);

-- --------------------------------------------------------------------------
-- Supplier catalogue: which supplier stocks which product, at what price
-- --------------------------------------------------------------------------
--
-- unit_cost and pack_size are made up but plausible; they do not need to
-- match products.cost_price, and deliberately sometimes do not - a supplier's
-- price is their own, not the shop's last recorded cost.
WITH wanted (supplier_name, sku, unit_cost, pack_size, is_preferred) AS (
    VALUES
        -- Dairy Direct Ltd: the preferred dairy supplier, even where dearer.
        ('Dairy Direct Ltd',       '2002-1001', 400.00, 12, TRUE),   -- Full Cream Milk (preferred, dearer than Fresh Farms below)
        ('Dairy Direct Ltd',       '2002-1004', 1150.00, 6, FALSE),  -- Butter
        ('Dairy Direct Ltd',       '2002-1003', 950.00, 6, TRUE),    -- Cheddar (preferred, dearer than Value Wholesale below)

        -- Fresh Farms Produce: produce, plus a cheaper (non-preferred) milk
        -- offer that exercises the "preferred wins even when dearer" rule.
        ('Fresh Farms Produce',    '2004-1001', 190.00, 1, FALSE),   -- Bananas
        ('Fresh Farms Produce',    '2004-1002', 250.00, 1, FALSE),   -- Tomatoes
        ('Fresh Farms Produce',    '2004-1004', 320.00, 6, FALSE),   -- Carrots
        ('Fresh Farms Produce',    '2002-1001', 390.00, 12, FALSE),  -- Full Cream Milk (cheaper, not preferred)

        -- Golden Bakery Supplies: bread only.
        ('Golden Bakery Supplies', '1234-2345', 240.00, 1, FALSE),   -- Sourdough

        -- Prime Meats & Poultry: eggs and chicken. Chicken Breast alone does
        -- not clear this supplier's minimum - see header.
        ('Prime Meats & Poultry',  '2003-1001', 470.00, 1, FALSE),   -- Chicken Eggs
        ('Prime Meats & Poultry',  '2003-1002', 1600.00, 1, TRUE),   -- Chicken Breast

        -- Value Wholesale Co: the cheaper, non-preferred cheddar offer, plus
        -- its own dairy/ambient range.
        ('Value Wholesale Co',     '2002-1002', 55.00, 12, FALSE),   -- Set Yoghurt
        ('Value Wholesale Co',     '2002-1820', 1400.00, 6, FALSE),  -- Oat Milk
        ('Value Wholesale Co',     '2005-1000', 480.00, 1, FALSE),   -- Mozzarella
        ('Value Wholesale Co',     '2002-1003', 900.00, 12, FALSE)   -- Cheddar (cheaper, not preferred)
),
resolved AS (
    SELECT s.id AS supplier_id, p.id AS product_id, w.unit_cost, w.pack_size, w.is_preferred
    FROM wanted w
    JOIN suppliers s ON s.name = w.supplier_name
    JOIN products p ON p.sku = w.sku
    -- Skip anything already created by a previous run, and skip silently
    -- rather than failing if a named SKU is ever missing from the catalogue.
    WHERE NOT EXISTS (
        SELECT 1 FROM supplier_products sp
        WHERE sp.supplier_id = s.id AND sp.product_id = p.id
    )
)
INSERT INTO supplier_products (
    supplier_id, product_id, unit_cost, pack_size, is_preferred, created_by
)
SELECT supplier_id, product_id, unit_cost, pack_size, is_preferred, 'seed'
FROM resolved;

COMMIT;
