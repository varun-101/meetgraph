"use client";

/** Shared primitives — vault-graphite theme (see globals.css). */
import type { MeetingStatus } from "@/lib/types";

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-edge bg-surface ${className}`}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
}) {
  const styles = {
    primary:
      "bg-accent text-accent-ink hover:bg-accent-dim font-medium",
    ghost:
      "border border-edge-strong text-ink-dim hover:bg-hover hover:text-ink",
    danger: "border border-danger/40 text-danger hover:bg-danger/10",
  }[variant];
  return (
    <button
      className={`rounded-md px-3.5 py-1.5 text-sm transition-colors disabled:opacity-40 disabled:pointer-events-none ${styles} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-edge bg-raised px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent-dim focus:outline-none ${props.className ?? ""}`}
    />
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-danger/40 bg-danger/10 px-3.5 py-2.5 text-sm text-danger"
    >
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-edge py-14 text-center">
      <p className="text-sm text-ink-dim">{title}</p>
      {hint && <p className="text-xs text-faint">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 py-10 justify-center text-muted text-sm">
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-edge-strong border-t-accent"
      />
      {label ?? "Loading…"}
    </div>
  );
}

const STATUS_STYLES: Record<MeetingStatus, string> = {
  scheduled: "border-edge-strong text-muted",
  live: "border-live/50 text-live",
  processing: "border-warn/50 text-warn",
  ready: "border-accent/50 text-accent",
};

export function StatusChip({ status }: { status: MeetingStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider ${STATUS_STYLES[status] ?? "border-edge-strong text-muted"}`}
    >
      {status === "live" && (
        <span
          aria-hidden
          className="size-1.5 rounded-full bg-live animate-pulse-dot"
        />
      )}
      {status}
    </span>
  );
}
