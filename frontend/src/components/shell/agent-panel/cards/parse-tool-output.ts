/**
 * Normalise a tool part's `output` into something a card can inspect.
 *
 * After gate 33 the streamed `tool-output-available.output` is already a JSON
 * object/array (pydantic-ai's `tool_return_output` passes a dict through
 * unchanged). But `success-card.tsx` shows the wire has also carried a JSON
 * *string* in the past, so this tolerates both. It never throws: an
 * unparseable string comes back as-is and the caller's type guard rejects it,
 * routing to <FallbackCard>.
 */
export function parseToolOutput(output: unknown): unknown {
  if (typeof output === "string") {
    try {
      return JSON.parse(output);
    } catch {
      return output;
    }
  }
  return output;
}
