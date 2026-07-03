"use client";

/** Landing page. The hero's right half is the product thesis in miniature:
 *  an attributed transcript becoming a cited answer (the "memory ledger").
 *  Everything else stays quiet — mono pipeline strip, ruled claim rows. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

const REPO = "https://github.com/varun-101/meetgraph";

/* Staggered reveal order for the ledger (seconds). */
const T = [0.3, 0.75, 1.2, 1.9, 2.5, 3.1];

export default function Landing() {
  const [authed, setAuthed] = useState(false);
  useEffect(() => setAuthed(Boolean(getToken())), []);

  return (
    <div className="min-h-screen">
      {/* nav */}
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <span className="font-mono text-sm font-medium tracking-tight text-ink">
          meet<span className="text-accent">graph</span>
        </span>
        <nav className="flex items-center gap-5 text-sm">
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="text-muted transition-colors hover:text-ink"
          >
            GitHub
          </a>
          <Link
            href={authed ? "/dashboard" : "/login"}
            className="rounded-md border border-edge-strong px-3.5 py-1.5 text-ink-dim transition-colors hover:bg-hover hover:text-ink"
          >
            {authed ? "Open dashboard" : "Sign in"}
          </Link>
        </nav>
      </header>

      {/* hero */}
      <section className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-6 pb-20 pt-14 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
        <div>
          <p className="mb-5 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            self-hosted meeting intelligence
          </p>
          <h1 className="text-4xl font-bold leading-[1.06] tracking-tight text-ink sm:text-5xl">
            Meetings evaporate.
            <br />
            Yours won&rsquo;t.
          </h1>
          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-ink-dim">
            meetgraph hosts the call on your infrastructure, captures every
            speaker on their own audio track, and turns each meeting into a
            knowledge graph — decisions, owners, deadlines — that answers
            questions with citations.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href={authed ? "/dashboard" : "/register"}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-dim"
            >
              {authed ? "Open dashboard" : "Create a workspace"}
            </Link>
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-edge-strong px-5 py-2.5 text-sm text-ink-dim transition-colors hover:bg-hover hover:text-ink"
            >
              View the source
            </a>
          </div>
          <p className="mt-6 font-mono text-[11px] text-faint">
            FastAPI · Postgres · LiveKit · cognee — one box, one database
          </p>
        </div>

        {/* the memory ledger */}
        <figure
          aria-label="A meeting transcript becoming a cited answer"
          className="rounded-xl border border-edge bg-surface shadow-2xl shadow-black/40"
        >
          <figcaption className="flex items-center justify-between border-b border-edge px-5 py-3 font-mono text-[11px] text-faint">
            <span>meeting — q3 planning</span>
            <span>2026-07-03</span>
          </figcaption>
          <div className="space-y-4 px-5 py-5 font-mono text-[12.5px] leading-relaxed">
            <p className="rise" style={{ animationDelay: `${T[0]}s` }}>
              <span className="text-faint">[00:12]</span>{" "}
              <span className="text-info">Mia Manager:</span>{" "}
              <span className="text-ink-dim">
                After the load tests, I&rsquo;m moving the launch to September
                17th.
              </span>
            </p>
            <p className="rise" style={{ animationDelay: `${T[1]}s` }}>
              <span className="text-faint">[00:31]</span>{" "}
              <span className="text-warn">Max Member:</span>{" "}
              <span className="text-ink-dim">
                I&rsquo;ll finish the payment gateway by August 30th so QA gets
                a full week.
              </span>
            </p>

            <div
              className="rise border-t border-edge pt-4"
              style={{ animationDelay: `${T[2]}s` }}
            >
              <p>
                <span className="text-accent">›</span>{" "}
                <span className="text-ink">
                  what did we decide about the launch date?
                </span>
              </p>
            </div>

            <div
              className="rise rounded-md border-l-2 border-accent bg-raised px-4 py-3"
              style={{ animationDelay: `${T[3]}s` }}
            >
              <p className="font-sans text-[13px] leading-relaxed text-ink-dim">
                Launch moved to <span className="text-ink">September 17th</span>{" "}
                — decided by Mia Manager after the load-test review.
              </p>
              <p
                className="rise mt-2.5 text-[11px] text-faint"
                style={{ animationDelay: `${T[4]}s` }}
              >
                <span className="text-accent">⌁</span> cited — q3 planning,{" "}
                <span className="underline decoration-edge-strong underline-offset-2">
                  00:12
                </span>
              </p>
            </div>
          </div>
          <p
            className="rise border-t border-edge px-5 py-3 font-mono text-[11px] text-faint"
            style={{ animationDelay: `${T[5]}s` }}
          >
            answered from the knowledge graph · on your servers
          </p>
        </figure>
      </section>

      {/* pipeline strip */}
      <section className="border-y border-edge bg-surface/50">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <p className="text-center font-mono text-[11.5px] leading-relaxed tracking-wide text-muted sm:whitespace-nowrap">
            your room <span className="mx-2 text-faint">▸</span>
            per-speaker audio <span className="mx-2 text-faint">▸</span>
            attributed transcript <span className="mx-2 text-faint">▸</span>
            knowledge graph <span className="mx-2 text-faint">▸</span>
            <span className="text-accent">cited answers</span>
          </p>
        </div>
      </section>

      {/* claims */}
      <section className="mx-auto max-w-3xl px-6 py-20">
        <Claim
          label="attribution is a fact"
          body="Each participant is recorded on their own audio track. Who said
          what is captured, not inferred — no diarization model guessing
          voices apart."
        />
        <Claim
          label="nothing leaves your servers"
          body="Video, transcripts, and the graph live in your Postgres. The one
          external call — LLM inference — swaps for a self-hosted model with a
          single config change."
        />
        <Claim
          label="memory you can govern"
          body="Access is role-based down to the dataset. Every memory operation
          writes an audit row, and deleting a project's memory actually
          deletes it — graph, recordings, transcripts."
        />
        <Claim
          label="the meeting presents itself"
          body="An AI presenter joins your call, shares slides built from the
          graph, answers questions with citations, and files action items —
          always with the asker's permissions, never its own."
          last
        />
      </section>

      {/* close */}
      <section className="border-t border-edge">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 py-16 text-center">
          <p className="text-xl font-semibold tracking-tight text-ink">
            Run it on your own box.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link
              href={authed ? "/dashboard" : "/register"}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-dim"
            >
              {authed ? "Open dashboard" : "Create a workspace"}
            </Link>
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-edge-strong px-5 py-2.5 text-sm text-ink-dim transition-colors hover:bg-hover hover:text-ink"
            >
              Read the quickstart
            </a>
          </div>
          <p className="font-mono text-[11px] text-faint">
            built on{" "}
            <a
              href="https://github.com/topoteretes/cognee"
              target="_blank"
              rel="noreferrer"
              className="underline decoration-edge-strong underline-offset-2 hover:text-muted"
            >
              cognee
            </a>{" "}
            for the cognee hackathon · 2026
          </p>
        </div>
      </section>
    </div>
  );
}

function Claim({
  label,
  body,
  last = false,
}: {
  label: string;
  body: string;
  last?: boolean;
}) {
  return (
    <div
      className={`grid grid-cols-1 gap-3 py-8 sm:grid-cols-[220px_1fr] sm:gap-8 ${
        last ? "" : "border-b border-edge"
      }`}
    >
      <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-accent">
        {label}
      </h2>
      <p className="text-[15px] leading-relaxed text-ink-dim">{body}</p>
    </div>
  );
}
