/**
 * The one raw `fetch` the agent panel needs — starting a new conversation.
 * Lives here (not in agent-panel.tsx) because ESLint's `no-restricted-imports`
 * rule confines `fetch` to `src/lib/api/**` and the proxy route; `useChat`'s
 * own transport calls are exempt as a documented client library, but this
 * call is code this repo wrote, so it goes through the sanctioned path.
 */
export async function startAgentConversation(): Promise<number> {
  const response = await fetch("/api/agent/conversations", { method: "POST" });
  const data = await response.json();
  return data.conversation_id;
}
