# thunderid-seed/

The login server's configuration for the Aisle demo box, as two SQLite database files.

- `configdb.db`  — applications, resource servers, roles, permissions, flows, themes
- `entitydb.db`  — the accounts: the built-in `admin`, the `judge` demo user, and the AI agent

`../scripts/seed.sh` copies these into the login server's storage the first time the box
starts, so nobody has to run an import wizard.

**These are committed to a public repository on purpose, and that was checked rather than
assumed.** Every credential inside is a PBKDF2 hash (600,000 iterations, per-entity salt),
never readable text. The reasoning, the rebuild procedure, and the scanner that enforces it
are in `../seed-build/README.md`.

Do not hand-edit them. Rebuild with `../seed-build/`.
