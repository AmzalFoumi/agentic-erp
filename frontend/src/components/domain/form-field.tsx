export const FIELD_CLASS =
  "h-control w-full rounded-(--radius) border border-input bg-card px-3 text-sm text-foreground aria-invalid:border-destructive";

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <div className="mt-1 text-xs text-destructive">{message}</div>;
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-(--radius) border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </div>
  );
}
