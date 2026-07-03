"use client";

/** Ask the org memory (P3/P4): cited Q&A over allowed datasets only. */
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import Shell, { useMe } from "@/components/shell";
import { Button, Card, ErrorBanner, Input } from "@/components/ui";
import { searchMemory } from "@/lib/api";
import type { Citation, SearchResponse } from "@/lib/types";

export default function SearchPage() {
  return (
    <Shell>
      <Search />
    </Shell>
  );
}

function Search() {
  const { me, orgId } = useMe();
  const [query, setQuery] = useState("");
  const [projectId, setProjectId] = useState<string>("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const projects = me.projects.filter((p) => !orgId || p.org_id === orgId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orgId || !query.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await searchMemory({
        org_id: orgId,
        project_id: projectId || undefined,
        query: query.trim(),
      });
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-lg font-semibold text-ink">Ask the memory</h1>
      <p className="mb-6 text-sm text-muted">
        &ldquo;What did we decide about X, who owns it, and why&rdquo; —
        answered with citations from your meetings.
      </p>

      <form onSubmit={submit} className="mb-6 flex gap-2">
        <Input
          placeholder="What did we decide about the launch date?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <select
          aria-label="Project scope"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="shrink-0 rounded-md border border-edge bg-raised px-2.5 text-sm text-ink-dim focus:outline-none focus:border-accent-dim"
        >
          <option value="">All my projects</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name ?? p.project_id.slice(0, 8)}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={busy || !query.trim()}>
          {busy ? "Asking…" : "Ask"}
        </Button>
      </form>

      {error && <ErrorBanner message={error} />}
      {busy && (
        <p className="animate-pulse text-sm text-muted">
          Querying the knowledge graph…
        </p>
      )}

      {result && (
        <div className="space-y-4">
          <Card className="p-5">
            {result.answer ? (
              <div className="markdown text-sm">
                <ReactMarkdown>{result.answer}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-muted">
                No answer found in the current scope.
              </p>
            )}
          </Card>
          {result.citations.length > 0 && (
            <div>
              <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-faint">
                Sources
              </h2>
              <ul className="space-y-1.5">
                {result.citations.map((c, i) => (
                  <CitationCard key={i} citation={c} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation | string }) {
  if (typeof citation === "string") {
    return (
      <li className="rounded-md border border-edge bg-raised px-3.5 py-2.5 text-xs text-muted">
        {citation}
      </li>
    );
  }
  return (
    <li className="rounded-md border border-edge bg-raised px-3.5 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-xs font-medium text-info">
          {citation.source ?? "meeting"}
        </span>
        {citation.date && (
          <span className="font-mono text-[10px] text-faint">
            {citation.date}
          </span>
        )}
      </div>
      {citation.snippet && (
        <p className="mt-1 text-xs leading-relaxed text-muted">
          &ldquo;{citation.snippet}&rdquo;
        </p>
      )}
    </li>
  );
}
