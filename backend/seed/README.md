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
