"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { ChatMode } from "../chat-mode";

/**
 * Carries the panel's docked/expanded mode to the response cards. The panel
 * already knows its mode (chat-shell.tsx passes it to AgentPanel); this context
 * hands it to cards nested inside MessageList without threading a prop through
 * every layer. Default "docked" — the narrow layout — so a card rendered
 * outside a provider (a test, a stray mount) degrades to the safe compact form.
 */
const ChatModeContext = createContext<ChatMode>("docked");

export function ChatModeProvider({
  mode,
  children,
}: {
  mode: ChatMode;
  children: ReactNode;
}) {
  return <ChatModeContext.Provider value={mode}>{children}</ChatModeContext.Provider>;
}

export function useChatMode(): ChatMode {
  return useContext(ChatModeContext);
}
