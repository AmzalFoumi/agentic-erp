/**
 * The two full-page error states from the error-state table in
 * docs/FRONTEND-PLAN.md: a real API error response, or (via error.tsx
 * boundaries) the backend not responding at all. Never render an empty
 * list to paper over either — see the "never fake an empty list" rule.
 */
export function ApiErrorState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-stack rounded-(--radius) border border-dashed border-border p-16 text-center">
      <div className="text-sm font-semibold">{title}</div>
      <div className="max-w-sm text-sm text-muted-foreground">{detail}</div>
      {action}
    </div>
  );
}
