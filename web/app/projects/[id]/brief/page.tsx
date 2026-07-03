"use client";

/** Pre-meeting brief (P3): markdown rendered from /memory/brief. */
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import Shell from "@/components/shell";
import { Card, ErrorBanner, Spinner } from "@/components/ui";
import { getBrief } from "@/lib/api";

export default function BriefPage() {
  return (
    <Shell>
      <Brief />
    </Shell>
  );
}

function Brief() {
  const { id } = useParams<{ id: string }>();
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ cached?: boolean; generated_at?: string }>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBrief(id)
      .then((b) => {
        setMarkdown(b.markdown);
        setMeta({ cached: b.cached, generated_at: b.generated_at });
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Brief unavailable"),
      );
  }, [id]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-lg font-semibold text-ink">
        Pre-meeting brief
      </h1>
      <p className="mb-6 text-sm text-muted">
        Recent decisions, open action items, and active topics — generated
        from this project&apos;s meeting memory.
        {meta.generated_at && (
          <span className="ml-2 font-mono text-[11px] text-faint">
            {meta.cached ? "cached · " : "fresh · "}
            {new Date(meta.generated_at).toLocaleString()}
          </span>
        )}
      </p>
      {error ? (
        <ErrorBanner message={error} />
      ) : markdown === null ? (
        <Spinner label="Generating brief from the knowledge graph…" />
      ) : (
        <Card className="p-6">
          <div className="markdown">
            <ReactMarkdown>
              {markdown || "_No memory for this project yet._"}
            </ReactMarkdown>
          </div>
        </Card>
      )}
    </div>
  );
}
