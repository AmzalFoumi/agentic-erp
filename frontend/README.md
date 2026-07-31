## REMEMBER - this file has oler existing README.md content and the nextjs default README.md combined (Manually copied back by developer after create-next-app replaced it). Check at next pass to protect original content.


This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.


Project specific - added back by developer - Amzal

# Frontend

A **Next.js** app for the inventory manager, talking to the FastAPI adapter at `backend/api/`. It is
a client of the API and nothing more — no business rules live here, for the same reason none live in
`backend/api/` or `backend/mcp_server/`.

Nothing is scaffolded yet; that happens at Gate 9. Check `docs/PLAN.md`'s progress table for the
current gate.

## Read these before writing any code here

This file is a **pointer, not a second copy**. Everything that used to be duplicated here is now
recorded once, where it is enforced:

| What | Where |
|---|---|
| Gates 9–13, the API capability inventory, and the **NOT-SUPPORTED list** | `docs/FRONTEND-PLAN.md` |
| Design tokens, density axis, LKR money format, timestamp format | `frontend/DESIGN.md` (from Gate 11) |
| Backend architecture decisions and MCP transport | `docs/BACKEND-PLAN.md` |
| The auth deferral and what ends it | `docs/AUTH-PLAN.md` |
| Live API reference | `uvicorn api.main:app --reload` from `backend/`, then <http://127.0.0.1:8000/docs> |

The **capability inventory** in `docs/FRONTEND-PLAN.md` is the one to read first. It lists what the API
deliberately does *not* support — no delete, no sorting, no reason capture on stock adjustment —
because building against a capability that isn't there is the most likely way to waste a gate.

## The trap that has bitten every layer of this project

**Money arrives as a JSON string, not a number.** `"18.00"`, not `18.00`. This is not an oversight —
`18.00` parsed as float64 is `17.999999999999996`, and a system that prints shelf prices cannot
accept that. Parse with a decimal library, never `parseFloat`, and never hand the value to
`Intl.NumberFormat` with `style: "currency"`.

