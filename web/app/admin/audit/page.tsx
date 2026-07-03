"use client";

/** Admin audit log (P5, §4.5): every memory op, newest first. */
import { useEffect, useState } from "react";
import Shell, { useMe } from "@/components/shell";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { getAudit } from "@/lib/api";
import type { AuditRow } from "@/lib/types";

const OP_TINT: Record<string, string> = {
  search: "text-info",
  add: "text-accent",
  cognify: "text-warn",
  forget: "text-danger",
  export: "text-muted",
};

export default function AuditPage() {
  return (
    <Shell>
      <Audit />
    </Shell>
  );
}

function Audit() {
  const { orgId } = useMe();
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    setRows(null);
    getAudit(orgId)
      .then(setRows)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Audit log unavailable");
        setRows([]);
      });
  }, [orgId]);

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-ink">Audit log</h1>
      <p className="mb-6 text-sm text-muted">
        Every memory operation in this organization — search, ingest, cognify,
        forget — with actor and dataset.
      </p>
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} />
        </div>
      )}
      {rows === null ? (
        <Spinner label="Loading audit log…" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No memory operations recorded yet"
          hint="Rows appear as soon as meetings are ingested or queried."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-edge">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge bg-raised text-left">
                <th className="px-4 py-2.5 font-medium text-muted">Time</th>
                <th className="px-4 py-2.5 font-medium text-muted">Op</th>
                <th className="px-4 py-2.5 font-medium text-muted">Dataset</th>
                <th className="px-4 py-2.5 font-medium text-muted">User</th>
                <th className="px-4 py-2.5 font-medium text-muted">Meeting</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-edge/60 last:border-0 hover:bg-hover/50"
                >
                  <td className="whitespace-nowrap px-4 py-2 text-muted">
                    {new Date(r.ts).toLocaleString()}
                  </td>
                  <td
                    className={`px-4 py-2 uppercase ${OP_TINT[r.op] ?? "text-muted"}`}
                  >
                    {r.op}
                  </td>
                  <td className="px-4 py-2 text-ink-dim">{r.dataset}</td>
                  <td className="px-4 py-2 text-muted">
                    {r.user_id ? r.user_id.slice(0, 8) : "system"}
                  </td>
                  <td className="px-4 py-2 text-muted">
                    {r.meeting_id ? r.meeting_id.slice(0, 8) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
