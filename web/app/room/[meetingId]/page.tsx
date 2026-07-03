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
import { Suspense, useEffect, useState } from "react";
import { Button, ErrorBanner, Spinner } from "@/components/ui";
import { getMeetingToken } from "@/lib/api";

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
      </LiveKitRoom>
    </div>
  );
}
