"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Density = "dense" | "comfortable";

/**
 * Toggles `data-density` on <html>. Dense is the server-rendered default
 * (see layout.tsx), so this only needs to read localStorage once on mount
 * to restore a returning user's choice — nothing here decides the first
 * paint. See frontend/DESIGN.md's Density section.
 */
function initialDensity(): Density {
  if (typeof window === "undefined") return "dense";
  const stored = window.localStorage.getItem("density");
  return stored === "dense" || stored === "comfortable" ? stored : "dense";
}

export function DensityToggle() {
  const [density, setDensity] = useState<Density>(initialDensity);

  useEffect(() => {
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  function apply(next: Density) {
    setDensity(next);
    document.documentElement.setAttribute("data-density", next);
    window.localStorage.setItem("density", next);
  }

  return (
    <div className="flex overflow-hidden rounded-(--radius) border border-border">
      {(["dense", "comfortable"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => apply(option)}
          className={cn(
            "px-3 py-1 text-xs capitalize",
            density === option
              ? "bg-primary text-primary-foreground"
              : "bg-card text-foreground hover:bg-secondary",
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
