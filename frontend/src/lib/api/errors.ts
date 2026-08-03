/**
 * The API's error envelope — the one part of the contract that is hand-written.
 *
 * ### Why this file is not generated
 *
 * Everything else in `src/lib/api` comes from `/openapi.json`. Error responses
 * do not, because `backend/api/errors.py` builds them as raw `JSONResponse`
 * dicts rather than declaring a Pydantic response model. FastAPI documents what
 * it is told about, so the error shape is invisible to the generator and the
 * typed client's error branch would otherwise be `unknown`.
 *
 * That makes this the one place where the frontend restates the backend, which
 * is exactly the thing the rest of this gate exists to avoid. It is written
 * down here, in one module, so the debt is visible and small. The real fix is a
 * shared response model in `backend/api/` — a backend gate, not something to
 * smuggle into frontend work.
 *
 * ### Why the discriminator is the body, not the status code
 *
 * A missing product and a mistyped URL are both 404. There is no better code
 * for either, so every error response — ours and the framework's — carries an
 * `error` field naming the specific failure. Switch on that, never on the
 * status alone. See the long comment at the top of `backend/api/errors.py`.
 */

/**
 * Every value the backend's `error` field can take. Closed on purpose: written
 * as a union rather than `string`, so a `switch` over it can be checked for
 * exhaustiveness and adding a case becomes a compile error rather than a
 * silently unhandled branch.
 *
 * The first five are domain errors raised by `backend/services/`; the last five
 * are framework failures that `errors.py` reshapes into the same envelope so
 * there is one error format in the whole API.
 */
export type ApiErrorCode =
  // Raised by services/ — see backend/core/exceptions.py
  | "NotFoundError" // 404 — the row does not exist
  | "DuplicateError" // 409 — e.g. that SKU is taken
  | "ValidationError" // 400 — a business rule said no ("only 2 in stock")
  | "PermissionDeniedError" // 403 — known caller, refused. Never 401
  | "DomainError" // 400 — catch-all for an unmapped domain error
  // Reshaped framework errors — see backend/api/errors.py
  | "RequestValidationError" // 422 — the request did not match the schema
  | "RouteNotFound" // 404 — no route matched. Not a missing product
  | "MethodNotAllowed" // 405
  | "NotAuthenticated" // 401 — cannot occur until auth lands
  | "HTTPError"; // any other framework status

/**
 * The response body of every failed request.
 */
export interface ApiError {
  /** Which failure. The discriminator — switch on this. */
  error: ApiErrorCode;
  /**
   * One human-readable sentence, safe to show. Service messages are written
   * for the shopkeeper ("Cannot remove 5 of RICE-1: only 2 in stock.") and
   * contain no internals or SQL. Right for a toast or a log line.
   */
  detail: string;
  /**
   * Present only on `RequestValidationError`: a `{field: message}` map, so form
   * errors go under their own inputs instead of into a single banner.
   *
   * This exists because the alternative — splitting `detail` on `"; "` and
   * `": "` — breaks the moment a validation message contains either separator,
   * and Pydantic's messages are not written with that constraint in mind.
   */
  fields?: Record<string, string>;
}

/**
 * Narrow an unknown value to `ApiError`.
 *
 * `openapi-fetch` returns `{ data, error }` and hands back the parsed body on
 * failure without knowing its shape, so this is the guard that turns it into
 * something the compiler will let you switch on.
 *
 * It checks structure rather than trusting the type assertion, because the body
 * genuinely could be anything — a proxy error page, a crash before the handlers
 * run. Anything that fails this check is a transport or infrastructure problem,
 * not a domain failure, and should be surfaced as such.
 */
export function isApiError(value: unknown): value is ApiError {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.error === "string" && typeof candidate.detail === "string"
  );
}
