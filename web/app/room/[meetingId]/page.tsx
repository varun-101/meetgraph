"use client";

/** LiveKit room (P1). Client component — WebRTC needs the browser.
 *  Members authenticate normally; guests arrive with ?guest_token=... */
import "@livekit/components-styles";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  VideoConference,
} from "@livekit/components-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import {
  commandPresenter,
  getMeetingToken,
  getPresenterStatus,
  nextPresenterSlide,
  startPresenter,
  stopPresenter,
  type PresenterStatus,
} from "@/lib/api";

export default function RoomPage() {
  return (
    <Suspense fallback={<Spinner label="Preparing room…" />}>
      <Room />
    </Suspense>
  );
}

function Room() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const guestToken = search.get("guest_token") ?? undefined;

  const [token, setToken] = useState<string | null>(null);
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMeetingToken(meetingId, guestToken)
      .then((r) => {
        setToken(r.token);
        setServerUrl(
          process.env.NEXT_PUBLIC_LIVEKIT_URL ?? r.livekit_url,
        );
      })
      .catch((e) =>
        setError(
          e instanceof Error ? e.message : "Could not join this meeting",
        ),
      );
  }, [meetingId, guestToken]);

  if (error)
    return (
      <div className="mx-auto max-w-lg space-y-4 pt-24 px-6">
        <ErrorBanner message={error} />
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          Back to dashboard
        </Button>
      </div>
    );
  if (!token || !serverUrl) return <Spinner label="Joining room…" />;

  return (
    <div className="h-screen" data-lk-theme="default">
      <LiveKitRoom
        token={token}
        serverUrl={serverUrl}
        connect
        audio
        video
        onDisconnected={() => router.push(guestToken ? "/" : "/dashboard")}
      >
        <VideoConference />
        <RoomAudioRenderer />
        {!guestToken && <PresenterBar meetingId={meetingId} />}
      </LiveKitRoom>
    </div>
  );
}

/** Floating host controls for the memory-backed presenter bot. Visible to all
 *  members; the API 403s non-managers. */
function PresenterBar({ meetingId }: { meetingId: string }) {
  const [status, setStatus] = useState<PresenterStatus>({ status: "none" });
  const [note, setNote] = useState<string | null>(null);
  const [ask, setAsk] = useState("");
  const noteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const s = await getPresenterStatus(meetingId);
        if (alive) setStatus(s);
      } catch {
        /* room may not be registered yet — keep last state */
      }
    };
    void poll();
    const iv = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, [meetingId]);

  const flash = (msg: string) => {
    setNote(msg);
    if (noteTimer.current) clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => setNote(null), 4000);
  };

  const call = async (fn: () => Promise<unknown>, optimistic?: PresenterStatus) => {
    try {
      await fn();
      if (optimistic) setStatus(optimistic);
    } catch (e) {
      flash(e instanceof Error ? e.message : "Request failed");
    }
  };

  const busy = status.status === "preparing";
  const live = status.status === "live";

  return (
    <div className="pointer-events-auto fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-edge-strong bg-surface/95 px-3 py-2 shadow-xl backdrop-blur">
      {note && <span className="px-1 text-xs text-danger">{note}</span>}
      {status.status === "stopped" && status.error && !note && (
        <span className="max-w-64 truncate px-1 text-xs text-danger" title={status.error}>
          presenter failed: {status.error}
        </span>
      )}
      {!live && !busy && (
        <button
          onClick={() =>
            call(() => startPresenter(meetingId), { status: "preparing" })
          }
          className="rounded-full bg-accent px-3.5 py-1.5 text-xs font-medium text-accent-ink hover:bg-accent-dim"
        >
          Present from memory
        </button>
      )}
      {busy && (
        <span className="flex items-center gap-2 px-2 text-xs text-warn">
          <span className="size-3 animate-spin rounded-full border-2 border-edge-strong border-t-warn" />
          Preparing deck…
        </span>
      )}
      {live && (
        <>
          <span className="px-1.5 font-mono text-[11px] text-accent">
            {status.mode && status.mode !== "deck"
              ? `browsing: ${status.mode}`
              : `slide ${(status.current_slide ?? 0) + 1}/${status.slide_count ?? "?"}`}
          </span>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const text = ask.trim();
              if (!text) return;
              setAsk("");
              void call(() => commandPresenter(meetingId, text));
            }}
          >
            <input
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              placeholder={
                status.handling_command
                  ? "Presenter is thinking…"
                  : "Ask the presenter…"
              }
              disabled={status.handling_command}
              className="w-52 rounded-full border border-edge bg-raised px-3 py-1.5 text-xs text-ink placeholder:text-faint focus:border-accent-dim focus:outline-none disabled:opacity-60"
            />
          </form>
          {status.handling_command && (
            <span className="size-3 animate-spin rounded-full border-2 border-edge-strong border-t-accent" />
          )}
          <button
            onClick={() => call(() => nextPresenterSlide(meetingId))}
            className="rounded-full border border-edge-strong px-3 py-1.5 text-xs text-ink-dim hover:bg-hover"
          >
            Next
          </button>
          <button
            onClick={() =>
              call(() => stopPresenter(meetingId), { status: "stopped" })
            }
            className="rounded-full border border-danger/40 px-3 py-1.5 text-xs text-danger hover:bg-danger/10"
          >
            Stop
          </button>
        </>
      )}
    </div>
  );
}
