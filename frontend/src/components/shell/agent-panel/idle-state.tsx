"use client";

const EXAMPLES = [
  "What's low on stock right now?",
  "Add 8 units to Sourdough loaf 800g",
  "Create a new product for oat milk",
];

export function IdleState({ onPickExample }: { onPickExample: (text: string) => void }) {
  return (
    <div className="flex flex-col gap-stack">
      <p className="text-sm text-muted-foreground">
        Ask it to look something up or make a change. It can do exactly what the forms can do —
        nothing more.
      </p>
      <div className="flex flex-col gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onPickExample(example)}
            className="rounded-(--radius) border border-border bg-secondary px-3 py-2 text-left text-sm text-secondary-foreground hover:bg-accent"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
