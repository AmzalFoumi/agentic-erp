# `backend/seed/` — hand-run data snapshots

Added 2026-08-27, at the start of gate 27.

## What lives here

SQL files that put **data** into the database. Nothing here is a migration.

The distinction matters, because this project already has a folder that looks
similar and is not:

| | `backend/alembic/versions/` | `backend/seed/` (this folder) |
|---|---|---|
| Changes | the **shape** of the database (tables, columns, RLS) | the **contents** (rows) |
| Run by | `alembic upgrade head` | a human, deliberately, once |
| Run in CI | yes | never |
| Run by the demo box | no — see `docs/DEPLOY-PLAN.md` | never |
| Ordered | yes, each one knows its predecessor | no, each is standalone |

## Why data snapshots exist at all

Gate 28 makes `inventory_lots` the source of truth for stock and reduces
`products.quantity_on_hand` to a summary the service layer maintains. Reseeding
the catalogue with real expiry dates is what makes the spoilage feature
demonstrable — a lot expiring tomorrow is the whole point.

Reseeding means deleting what is there. A snapshot taken first is the
difference between "we changed the demo data" and "we lost the demo data".

## The rule for adding one

Name it `YYYY-MM-DD-<what>.sql` and write a header comment saying what it is a
snapshot **of**, **when** it was taken, and what to be careful of on restore.
A file here with no header is worse than no file: nobody will dare run it.

Two things every snapshot of a table with a `SERIAL` primary key must do, both
shown in `2026-08-27-products-snapshot.sql`:

- **Preserve explicit ids**, so anything referring to a row by id still resolves.
- **Move the sequence afterwards** with `setval`. Inserting explicit ids does
  not advance the counter that hands out new ones, so skipping this makes the
  very next insert fail on a duplicate primary key — some distance away from
  the cause, which makes it a nasty one to debug.

## 2026-08-27-dated-lots.sql

Gives the perishable products realistic delivery batches with expiry dates, so the spoilage
feature has something to find. Run it **after** migration `d5b93a17c204`.

Three things about it are deliberate and easy to get wrong if it is ever rewritten:

- **It splits, it does not delete.** Each dated batch is carved out of the same product's
  `OPENING` lot, so product ids survive and every product's total is unchanged. Nothing is
  destroyed, so nothing has to be restored.
- **Dates are `CURRENT_DATE + n`, never literal.** A fixed date is correct on the day it is
  written and wrong every day after — by demo day it would be a shop full of stock that
  expired last week.
- **It is idempotent.** Every insert is guarded on the lot code not already existing for
  that product, so re-running changes nothing.

The `2026-08-27-products-snapshot.sql` in this folder remains the "before" copy of the
catalogue, taken before any of this.
