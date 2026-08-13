/**
 * The one raw `fetch` the agent panel needs — starting a new conversation.
 * Lives here (not in agent-panel.tsx) because ESLint's `no-restricted-globals`
 * rule confines `fetch` to `src/lib/api/**` and the proxy route; `useChat`'s
 * own transport calls are exempt as a documented client library, but this
 * call is code this repo wrote, so it goes through the sanctioned path.
 */
export async function startAgentConversation(): Promise<number> {
  const response = await fetch("/api/agent/conversations", { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to start agent conversation: ${response.status}`);
  }
  const data: { conversation_id: number } = await response.json();
  return data.conversation_id;
}

/**
 * Fetches an existing conversation (parked approval or normal history) so a
 * page reload can resume it instead of abandoning it for a new one. Returns
 * `null` on 404 — the stored id no longer exists server-side — so the caller
 * can fall back to `startAgentConversation()`.
 */
export async function getAgentConversation(
  id: number,
): Promise<{ messages: unknown[]; pending_since: string | null } | null> {
  const response = await fetch(`/api/agent/conversations/${id}`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load agent conversation: ${response.status}`);
  }
  return response.json();
}
