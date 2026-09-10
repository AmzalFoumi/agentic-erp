"use client";

import { Component, type ReactNode } from "react";

/**
 * Belt and braces. Every card already parses defensively and returns
 * <FallbackCard> on a shape mismatch, so this should never fire — but a card
 * that throws for any other reason must not take the whole transcript down
 * mid-demo. React 19 still has no hook form of an error boundary, so this is a
 * class component.
 */
export class CardErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    // The fallback is silent by design; log so a card that throws mid-demo is
    // at least debuggable from the console.
    console.error("Response card threw, showing fallback:", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
