"use client";

/** Action tracker (P4): status dropdown syncs to API → append-only graph doc. */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/shell";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { getProjectActions, patchAction } from "@/lib/api";
import type { ActionItem } from "@/lib/types";

const STATUSES = ["open", "in_progress", "done"] as const;

const STATUS_TINT: Record<string, string> = {
  open: "text-info",
  in_progress: "text-warn",
  done: "text-accent",
};

export default function ActionsPage() {
  return (
    <Shell>
      <Actions />
    </Shell>
  );
}

function Actions() {
  const { id } = useParams<{ id: string }>();
  const [actions, setActions] = useState<ActionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProjectActions(id)
      .then(setActions)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load actions");
        setActions([]);
      });
  }, [id]);

  const update = async (actionId: string, status: string) => {
    const prev = actions;
    setActions(
      (a) => a?.map((x) => (x.id === actionId ? { ...x, status } : x)) ?? null,
    );
    try {
      await patchAction(actionId, status);
    } catch (e) {
      setActions(prev ?? null); // roll back optimistic update
      setError(e instanceof Error ? e.message : "Update failed");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-lg font-semibold text-ink">Action tracker</h1>
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} />
        </div>
      )}
      {actions === null ? (
        <Spinner label="Loading actions…" />
      ) : actions.length === 0 ? (
        <EmptyState
          title="No action items yet"
          hint="They're extracted automatically after each meeting."
        />
      ) : (
        <ul className="space-y-2">
          {actions.map((a) => (
            <li key={a.id}>
              <Card className="flex items-center gap-4 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-sm ${a.status === "done" ? "text-faint line-through" : "text-ink-dim"}`}
                  >
                    {a.text}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-faint">
                    {a.deadline
                      ? `due ${new Date(a.deadline).toLocaleDateString()}`
                      : "no deadline"}
                    {" · "}
                    <Link
                      href={`/meetings/${a.meeting_id}`}
                      className="hover:text-info"
                    >
                      source meeting
                    </Link>
                  </p>
                </div>
                <select
                  aria-label="Status"
                  value={a.status}
                  onChange={(e) => update(a.id, e.target.value)}
                  className={`rounded-md border border-edge bg-raised px-2 py-1 font-mono text-xs focus:outline-none focus:border-accent-dim ${STATUS_TINT[a.status] ?? "text-muted"}`}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
