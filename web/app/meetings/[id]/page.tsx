"use client";

/** Transcript viewer (P4): speaker-attributed utterances, speaker-colored,
 *  timestamps carry data-start for the future audio-seek hook. */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Shell from "@/components/shell";
import {
  Card,
  EmptyState,
  ErrorBanner,
  Spinner,
  StatusChip,
} from "@/components/ui";
import { getMeeting, getMeetingActions, getTranscript } from "@/lib/api";
import type { ActionItem, Meeting, Utterance } from "@/lib/types";

/* Speaker hues — their own family, never reused for status (globals.css). */
const SPEAKER_COLORS = [
  "#6ea8fe",
  "#d59bf6",
  "#f5b84b",
  "#5fd4d0",
  "#f490b1",
  "#a3d977",
];

function mmss(s: number): string {
  const t = Math.max(0, Math.floor(s));
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

export default function MeetingPage() {
  return (
    <Shell>
      <MeetingDetail />
    </Shell>
  );
}

function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [utterances, setUtterances] = useState<Utterance[] | null>(null);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [transcriptMissing, setTranscriptMissing] = useState(false);

  useEffect(() => {
    getMeeting(id)
      .then(setMeeting)
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
    getTranscript(id)
      .then((t) => setUtterances(t.utterances))
      .catch(() => {
        setUtterances([]);
        setTranscriptMissing(true);
      });
    getMeetingActions(id)
      .then(setActions)
      .catch(() => setActions([]));
  }, [id]);

  const speakerColor = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of utterances ?? []) {
      if (!map.has(u.speaker_identity))
        map.set(
          u.speaker_identity,
          SPEAKER_COLORS[map.size % SPEAKER_COLORS.length],
        );
    }
    return map;
  }, [utterances]);

  if (error)
    return (
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Link href="/dashboard" className="text-sm text-info hover:underline">
          ← Back to dashboard
        </Link>
      </div>
    );
  if (!meeting || utterances === null)
    return <Spinner label="Loading meeting…" />;

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_320px]">
      <section>
        <div className="mb-6 flex items-center gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold text-ink">
              {meeting.title}
            </h1>
            <p className="mt-0.5 font-mono text-[11px] text-faint">
              {meeting.started_at
                ? new Date(meeting.started_at).toLocaleString()
                : "not started"}
            </p>
          </div>
          <StatusChip status={meeting.status} />
        </div>

        {transcriptMissing ? (
          <EmptyState
            title={
              meeting.status === "processing"
                ? "Transcript is being generated…"
                : "No transcript yet"
            }
            hint={
              meeting.status === "processing"
                ? "Speech-to-text runs automatically after the meeting ends."
                : "The transcript appears here after the meeting is recorded."
            }
          />
        ) : (
          <ol className="space-y-4">
            {utterances.map((u, i) => {
              const color = speakerColor.get(u.speaker_identity) ?? "#8c96a8";
              const newSpeaker =
                i === 0 ||
                utterances[i - 1].speaker_identity !== u.speaker_identity;
              return (
                <li key={i} data-start={u.start} className="group flex gap-3">
                  <span className="w-12 shrink-0 pt-0.5 text-right font-mono text-[11px] text-faint group-hover:text-muted">
                    {mmss(u.start)}
                  </span>
                  <div
                    className="w-0.5 shrink-0 self-stretch rounded-full"
                    style={{ background: color, opacity: 0.6 }}
                  />
                  <div className="min-w-0">
                    {newSpeaker && (
                      <p
                        className="mb-0.5 text-xs font-semibold"
                        style={{ color }}
                      >
                        {u.speaker_name}
                      </p>
                    )}
                    <p className="text-sm leading-relaxed text-ink-dim">
                      {u.text}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <aside>
        <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-faint">
          Action items
        </h2>
        {actions.length === 0 ? (
          <p className="text-sm text-faint">None extracted.</p>
        ) : (
          <ul className="space-y-2">
            {actions.map((a) => (
              <li key={a.id}>
                <Card className="px-3.5 py-2.5">
                  <p className="text-sm text-ink-dim">{a.text}</p>
                  <p className="mt-1.5 font-mono text-[11px] text-faint">
                    {a.status}
                    {a.deadline &&
                      ` · due ${new Date(a.deadline).toLocaleDateString()}`}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        )}
        {meeting && (
          <Link
            href={`/projects/${meeting.project_id}/actions`}
            className="mt-3 block text-xs text-info hover:underline"
          >
            Open action tracker →
          </Link>
        )}
      </aside>
    </div>
  );
}
