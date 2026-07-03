"use client";

/** Landing page. Motion encodes the product, not decoration:
 *  - the word "evaporate." perpetually evaporates; "Yours won't." stays put
 *  - the memory ledger is a live loop: utterances TYPE while each speaker's
 *    own waveform pulses (per-track capture) → facts highlight → a mini
 *    knowledge graph draws itself → the query types → cited answer lands
 *  - an audit ticker scrolls the ops feed; claims reveal on scroll
 *  All JS-driven motion collapses to the final frame under reduced motion. */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/api";

const REPO = "https://github.com/varun-101/meetgraph";

/* ---------------- ledger timeline (one tick = 80ms) ---------------- */

const U1 = "After the load tests, I'm moving the launch to September 17th.".split(" ");
const U2 = "I'll finish the payment gateway by August 30th so QA gets a full week.".split(" ");
const QUERY = "what did we decide about the launch date?";

const TICK_MS = 80;
const U1_START = 8;
const U1_END = U1_START + U1.length; // one word per tick
const U2_START = U1_END + 7;
const U2_END = U2_START + U2.length;
const GRAPH_AT = U2_END + 8;
const Q_START = GRAPH_AT + 18;
const Q_END = Q_START + Math.ceil(QUERY.length / 2); // two chars per tick
const ANSWER_AT = Q_END + 6;
const CITE_AT = ANSWER_AT + 10;
const LOOP_AT = CITE_AT + 46;

export default function Landing() {
  const [authed, setAuthed] = useState(false);
  const [t, setT] = useState(0);

  useEffect(() => {
    setAuthed(Boolean(getToken()));
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setT(CITE_AT + 1); // final frame, no loop
      return;
    }
    const iv = setInterval(
      () => setT((v) => (v >= LOOP_AT ? 0 : v + 1)),
      TICK_MS,
    );
    return () => clearInterval(iv);
  }, []);

  const u1Words = Math.max(0, Math.min(U1.length, t - U1_START));
  const u2Words = Math.max(0, Math.min(U2.length, t - U2_START));
  const qChars = Math.max(0, Math.min(QUERY.length, (t - Q_START) * 2));
  const miaTalking = t >= U1_START && t < U1_END;
  const maxTalking = t >= U2_START && t < U2_END;
  const graphOn = t >= GRAPH_AT;
  const answerOn = t >= ANSWER_AT;
  const citeOn = t >= CITE_AT;
  // hide during the fade-out AND the first ticks after reset, so the loop
  // seam reads as a clean cut instead of a flash of empty card
  const fading = t >= LOOP_AT - 4 || t < 4;

  return (
    <div className="min-h-screen overflow-x-clip">
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
      <section className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-6 pb-20 pt-12 lg:grid-cols-[1.02fr_1fr] lg:pt-20">
        {/* ambient glow behind the ledger */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 top-8 hidden h-[480px] w-[480px] rounded-full lg:block"
          style={{
            background:
              "radial-gradient(closest-side, rgba(61,220,151,0.07), transparent)",
          }}
        />

        <div>
          <p className="rise mb-5 font-mono text-xs uppercase tracking-[0.18em] text-accent">
            self-hosted meeting intelligence
          </p>
          <h1 className="text-[2.6rem] font-bold leading-[1.04] tracking-tight text-ink sm:text-6xl">
            <span className="rise block" style={{ animationDelay: "0.1s" }}>
              Meetings{" "}
              <span aria-label="evaporate." className="whitespace-nowrap">
                {"evaporate.".split("").map((ch, i) => (
                  <span
                    key={i}
                    aria-hidden
                    className="evap text-muted"
                    style={{ "--d": `${i * 0.14}s` } as React.CSSProperties}
                  >
                    {ch}
                  </span>
                ))}
              </span>
            </span>
            <span className="rise block" style={{ animationDelay: "0.28s" }}>
              Yours won&rsquo;t<span className="text-accent">.</span>
            </span>
          </h1>
          <p
            className="rise mt-6 max-w-md text-[15px] leading-relaxed text-ink-dim"
            style={{ animationDelay: "0.45s" }}
          >
            meetgraph hosts the call on your infrastructure, captures every
            speaker on their own audio track, and turns each meeting into a
            knowledge graph — decisions, owners, deadlines — that answers
            questions with citations.
          </p>
          <div
            className="rise mt-8 flex flex-wrap items-center gap-3"
            style={{ animationDelay: "0.6s" }}
          >
            <Link
              href={authed ? "/dashboard" : "/register"}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-all hover:-translate-y-0.5 hover:bg-accent-dim hover:shadow-lg hover:shadow-accent/20"
            >
              {authed ? "Open dashboard" : "Create a workspace"}
            </Link>
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-edge-strong px-5 py-2.5 text-sm text-ink-dim transition-all hover:-translate-y-0.5 hover:bg-hover hover:text-ink"
            >
              View the source
            </a>
          </div>
          <p
            className="rise mt-6 font-mono text-[11px] text-faint"
            style={{ animationDelay: "0.75s" }}
          >
            FastAPI · Postgres · LiveKit · cognee — one box, one database
          </p>
        </div>

        {/* the memory ledger — live loop */}
        <figure
          aria-label="A meeting transcript becoming a cited answer"
          className={`rise relative rounded-xl border border-edge bg-surface shadow-2xl shadow-black/50 transition-opacity duration-500 ${
            fading ? "opacity-0" : "opacity-100"
          }`}
          style={{ animationDelay: "0.35s" }}
        >
          <figcaption className="flex items-center justify-between border-b border-edge px-5 py-3 font-mono text-[11px] text-faint">
            <span className="flex items-center gap-2">
              <span className="rec size-1.5 rounded-full bg-live" aria-hidden />
              meeting — q3 planning
            </span>
            <span>2026-07-03</span>
          </figcaption>

          <div className="min-h-[330px] space-y-4 px-5 py-5 font-mono text-[12.5px] leading-relaxed">
            {/* utterance 1 — Mia */}
            <div className={t >= U1_START ? "" : "invisible"}>
              <p className="mb-1 flex items-center gap-2 text-info">
                <span className={`wave ${miaTalking ? "on" : ""}`} aria-hidden>
                  <i /><i /><i /><i /><i />
                </span>
                Mia Manager
                <span className="text-faint">[00:12]</span>
              </p>
              <p className="pl-6 text-ink-dim">
                {U1.slice(0, u1Words).map((w, i) => (
                  <span
                    key={i}
                    className={
                      w === "September" || w === "17th."
                        ? `hl ${graphOn ? "on" : ""}`
                        : undefined
                    }
                  >
                    {w}{" "}
                  </span>
                ))}
              </p>
            </div>

            {/* utterance 2 — Max */}
            <div className={t >= U2_START ? "" : "invisible"}>
              <p className="mb-1 flex items-center gap-2 text-warn">
                <span className={`wave ${maxTalking ? "on" : ""}`} aria-hidden>
                  <i /><i /><i /><i /><i />
                </span>
                Max Member
                <span className="text-faint">[00:31]</span>
              </p>
              <p className="pl-6 text-ink-dim">
                {U2.slice(0, u2Words).map((w, i) => (
                  <span
                    key={i}
                    className={
                      w === "August" || w === "30th"
                        ? `hl ${graphOn ? "on" : ""}`
                        : undefined
                    }
                  >
                    {w}{" "}
                  </span>
                ))}
              </p>
            </div>

            {/* mini knowledge graph draws itself */}
            <div
              className={`flex items-center gap-0 pt-1 ${
                graphOn ? "" : "invisible"
              }`}
              aria-hidden
            >
              <GraphNode on={graphOn} delay={0} tone="accent">
                Decision · Sept 17
              </GraphNode>
              <span className="mx-1 block flex-1">
                <span
                  className={`gedge block ${graphOn ? "on" : ""}`}
                  style={{ transitionDelay: "0.2s" }}
                />
              </span>
              <GraphNode on={graphOn} delay={0.35} tone="info">
                Mia Manager
              </GraphNode>
              <span className="mx-1 block flex-1">
                <span
                  className={`gedge block ${graphOn ? "on" : ""}`}
                  style={{ transitionDelay: "0.6s" }}
                />
              </span>
              <GraphNode on={graphOn} delay={0.85} tone="warn">
                Action · Aug 30
              </GraphNode>
            </div>

            {/* query types itself */}
            <div
              className={`border-t border-edge pt-4 ${
                t >= Q_START ? "" : "invisible"
              }`}
            >
              <p>
                <span className="text-accent">›</span>{" "}
                <span className={`text-ink ${qChars < QUERY.length ? "caret" : ""}`}>
                  {QUERY.slice(0, qChars)}
                </span>
              </p>
            </div>

            {/* cited answer */}
            <div
              className={`rounded-md border-l-2 border-accent bg-raised px-4 py-3 transition-all duration-500 ${
                answerOn
                  ? "translate-y-0 opacity-100"
                  : "pointer-events-none translate-y-2 opacity-0"
              }`}
            >
              <p className="font-sans text-[13px] leading-relaxed text-ink-dim">
                Launch moved to <span className="text-ink">September 17th</span>{" "}
                — decided by Mia Manager after the load-test review.
              </p>
              <p
                className={`mt-2.5 text-[11px] text-faint transition-opacity duration-500 ${
                  citeOn ? "opacity-100" : "opacity-0"
                }`}
              >
                <span className="text-accent">⌁</span> cited — q3 planning,{" "}
                <span className="underline decoration-edge-strong underline-offset-2">
                  00:12
                </span>
              </p>
            </div>
          </div>

          <p className="border-t border-edge px-5 py-3 font-mono text-[11px] text-faint">
            answered from the knowledge graph · on your servers
          </p>
        </figure>
      </section>

      {/* pipeline strip — arrows pulse like data flowing */}
      <section className="border-y border-edge bg-surface/50">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <p className="text-center font-mono text-[11.5px] leading-relaxed tracking-wide text-muted sm:whitespace-nowrap">
            your room{" "}
            <span className="flow-sep mx-2" style={{ "--d": "0s" } as React.CSSProperties}>▸</span>
            per-speaker audio{" "}
            <span className="flow-sep mx-2" style={{ "--d": "0.35s" } as React.CSSProperties}>▸</span>
            attributed transcript{" "}
            <span className="flow-sep mx-2" style={{ "--d": "0.7s" } as React.CSSProperties}>▸</span>
            knowledge graph{" "}
            <span className="flow-sep mx-2" style={{ "--d": "1.05s" } as React.CSSProperties}>▸</span>
            <span className="text-accent">cited answers</span>
          </p>
        </div>
      </section>

      {/* claims — scroll-revealed rows */}
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

      {/* audit ticker — governance as texture */}
      <section
        aria-hidden
        className="overflow-hidden border-y border-edge bg-surface/40 py-3"
      >
        <div className="ticker font-mono text-[11px] text-faint">
          {[0, 1].map((copy) => (
            <span key={copy} className="flex shrink-0 items-center whitespace-nowrap">
              {TICKER_OPS.map((op, i) => (
                <span key={i} className="mx-5 flex items-center gap-2 whitespace-nowrap">
                  <span className={OP_TONE[op.kind]}>{op.kind}</span>
                  <span>{op.detail}</span>
                  <span className="text-edge-strong">/</span>
                </span>
              ))}
            </span>
          ))}
        </div>
      </section>

      {/* close */}
      <section>
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 py-16 text-center">
          <p className="text-xl font-semibold tracking-tight text-ink">
            Run it on your own box.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link
              href={authed ? "/dashboard" : "/register"}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-all hover:-translate-y-0.5 hover:bg-accent-dim hover:shadow-lg hover:shadow-accent/20"
            >
              {authed ? "Open dashboard" : "Create a workspace"}
            </Link>
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-edge-strong px-5 py-2.5 text-sm text-ink-dim transition-all hover:-translate-y-0.5 hover:bg-hover hover:text-ink"
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

/* ---------------- pieces ---------------- */

const TICKER_OPS = [
  { kind: "search", detail: "ds_apollo · manager@acme" },
  { kind: "cognify", detail: "ds_apollo · 1 meeting" },
  { kind: "add", detail: "action-status update" },
  { kind: "search", detail: "ds_zephyr · member@acme" },
  { kind: "forget", detail: "ds_orion · admin@acme" },
  { kind: "add", detail: "meeting transcript · 14 min" },
  { kind: "search", detail: "pre-meeting brief · cached" },
  { kind: "cognify", detail: "temporal graph rebuild" },
] as const;

const OP_TONE: Record<string, string> = {
  search: "text-info",
  add: "text-accent",
  cognify: "text-warn",
  forget: "text-danger",
};

function GraphNode({
  children,
  on,
  delay,
  tone,
}: {
  children: React.ReactNode;
  on: boolean;
  delay: number;
  tone: "accent" | "info" | "warn";
}) {
  const tones = {
    accent: "border-accent/50 text-accent",
    info: "border-info/50 text-info",
    warn: "border-warn/50 text-warn",
  };
  return (
    <span
      className={`gnode ${on ? "on" : ""} shrink-0 rounded-full border bg-raised px-2.5 py-1 text-[10px] ${tones[tone]}`}
      style={{ transitionDelay: `${delay}s` }}
    >
      {children}
    </span>
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
  const ref = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && setOn(true),
      { threshold: 0.35 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${on ? "on" : ""} grid grid-cols-1 gap-3 py-8 sm:grid-cols-[220px_1fr] sm:gap-8 ${
        last ? "" : "border-b border-edge"
      }`}
    >
      <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-accent">
        {label}
        <span className="eyebrow-line" aria-hidden />
      </h2>
      <p className="text-[15px] leading-relaxed text-ink-dim">{body}</p>
    </div>
  );
}
