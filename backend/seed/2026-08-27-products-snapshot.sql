-- Snapshot of public.products taken 2026-08-27, before gate 28 (lots) reseeds it.
--
-- WHY THIS FILE EXISTS
-- --------------------
-- Gate 28 introduces `inventory_lots` and makes lots the source of truth for
-- stock, with products.quantity_on_hand kept as a maintained summary. The
-- developer authorised deleting the current demo catalogue and reseeding it
-- once lots exist, so that the seeded data can carry real expiry dates and
-- demo the spoilage feature properly.
--
-- This file is the "before" copy, so nothing is lost if that reseed goes wrong
-- or has to be rolled back. It is a snapshot, NOT a migration: alembic never
-- runs it, CI never runs it, and the demo box never runs it. Restoring is a
-- deliberate act by a human.
--
-- WHAT IT CONTAINS
-- ----------------
-- 24 products, ids 139-162, as they stood on 2026-08-27. Audit timestamps
-- (created_at / updated_at) are deliberately NOT included: they have database
-- defaults, and restoring a snapshot is a new event, not a re-enactment of the
-- original one. created_by / updated_by ARE included, because they record who
-- made the row and that fact does not change on restore. The three values seen
-- there are 'api', 'mcp' and one real ThunderID subject id from gate 24.
--
-- Money is written unquoted (250.00, not '250.00') because these columns are
-- Numeric(10,2). Note this is the opposite of how the API serialises money -
-- the API returns a JSON *string* on purpose, to avoid float64 precision loss.
-- That is a transport decision; in SQL a numeric literal is exact already.
--
-- HOW TO RESTORE
-- --------------
-- Against the Supabase database, in a SQL editor or psql:
--
--     \i backend/seed/2026-08-27-products-snapshot.sql
--
-- The explicit ids are preserved so that anything referring to a product by id
-- (an agent conversation, a draft payload) still resolves after a restore. The
-- final statement is therefore REQUIRED: inserting explicit ids does not move
-- the sequence that hands out new ones, so without it the next INSERT would
-- collide with id 139 and fail on the primary key.

BEGIN;

INSERT INTO public.products
    (id, sku, name, category, unit, cost_price, sell_price, quantity_on_hand, reorder_level, created_by, updated_by)
VALUES
    (139, '1234-2345', 'Sourdough 800g',         'Breads',             'piece',   250.00,  400.00,  274,  25, 'api', '01a03e4b-8c43-79b8-a2a1-c9ccf73e9f57'),
    (140, '2001-1001', 'Basmati Rice 5kg',       'Grains',             'bag',    1850.00, 2400.00,   60,  20, 'api', 'api'),
    (141, '2001-1002', 'Red Rice 5kg',           'Grains',             'bag',    1200.00, 1650.00,    8,  20, 'api', 'api'),
    (142, '2001-1003', 'Wheat Flour 1kg',        'Grains',             'pack',    220.00,  310.00,  390,  40, 'api', 'mcp'),
    (143, '2002-1001', 'Full Cream Milk 1L',     'Dairy',              'carton',  380.00,  480.00,   12,  30, 'api', 'api'),
    (144, '2002-1002', 'Set Yoghurt 80g',        'Dairy',              'cup',      60.00,   95.00,  200,  60, 'api', 'api'),
    (145, '2002-1003', 'Cheddar Cheese 200g',    'Dairy',              'pack',    920.00, 1250.00,    3,  10, 'api', 'api'),
    (146, '2002-1004', 'Butter 227g',            'Dairy',              'pack',   1100.00, 1480.00,   25,  15, 'api', 'api'),
    (147, '2003-1001', 'Chicken Eggs (10)',      'Poultry',            'tray',    480.00,  620.00,   45,  20, 'api', 'api'),
    (148, '2003-1002', 'Chicken Breast 1kg',     'Poultry',            'pack',   1650.00, 2100.00,    6,  12, 'api', 'api'),
    (149, '2004-1001', 'Bananas Ambul 1kg',      'Produce',            'kg',      180.00,  260.00,   70,  25, 'api', 'api'),
    (150, '2004-1002', 'Tomatoes 1kg',           'Produce',            'kg',      240.00,  340.00,   18,  20, 'api', 'api'),
    (151, '2004-1003', 'Big Onions 1kg',         'Produce',            'kg',      290.00,  390.00,    0,  30, 'api', 'api'),
    (152, '2004-1004', 'Carrots 1kg',            'Produce',            'kg',      310.00,  420.00,   52,  20, 'api', 'api'),
    (153, '2005-1001', 'Coconut Oil 750ml',      'Cooking',            'bottle',  780.00,  990.00,   34,  15, 'api', 'api'),
    (154, '2005-1002', 'Sunflower Oil 1L',       'Cooking',            'bottle',  960.00, 1240.00,    9,  18, 'api', 'api'),
    (155, '2005-1003', 'Table Salt 400g',        'Cooking',            'pack',     70.00,  110.00,  160,  50, 'api', 'api'),
    (156, '2006-1001', 'Ceylon Black Tea 200g',  'Beverages',          'pack',    540.00,  720.00,   80,  25, 'api', 'api'),
    (157, '2006-1002', 'Ground Coffee 200g',     'Beverages',          'pack',   1450.00, 1890.00,    4,  10, 'api', 'api'),
    (158, '2006-1003', 'Sparkling Water 1.5L',   'Beverages',          'bottle',  150.00,  230.00,    0,  24, 'api', 'api'),
    (159, '2007-1001', 'Dish Soap 500ml',        'Household',          'bottle',  340.00,  460.00,   28,  12, 'api', 'api'),
    (160, '2003-1003', 'Beef',                   'produce',            'kg',     2000.00, 2500.00, 2000, 500, 'mcp', 'mcp'),
    (161, '2002-1820', 'Oat Milk',               'Dairy Alternatives', 'litre',  1500.00, 2000.00,  500, 100, 'mcp', 'mcp'),
    (162, '2005-1000', 'Mozzarella Cheese 250g', 'Dairy',              'pack',    500.00,  800.00,  120,  10, 'mcp', 'api');

-- Move the id sequence past the highest restored id. Without this, the next
-- product created through the API or the agent would be handed id 139 and fail.
SELECT setval(
    pg_get_serial_sequence('public.products', 'id'),
    (SELECT MAX(id) FROM public.products)
);

COMMIT;
