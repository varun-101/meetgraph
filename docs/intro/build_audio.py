"""Soundtrack for docs/intro/meetgraph-intro.webm.

- Voices (edge-tts): narrator (Sonia), Mia (Jenny), Max (Guy), presenter (Aria)
- SFX (numpy synth): ambient pad, scene whooshes, typing ticks, node pops,
  answer chime
- Mix at 48k mono -> mux into the webm (video packets copied, audio = Opus)
"""
import asyncio
import io
from pathlib import Path

import numpy as np

REPO = Path(r"d:\codes\cognee_hackathon\meetgraph")
VIDEO_IN = REPO / "docs" / "intro" / "meetgraph-intro.webm"
VIDEO_OUT = REPO / "docs" / "intro" / "meetgraph-intro-sound.webm"
SR = 48_000
DUR = 37.5  # slightly past the 37s video — players hold the end card
# Measured from the recording: first painted frame lands at t=0.12s, so the
# page's CSS animation clock runs 120ms behind the video clock.
OFFSET = 0.12

NARRATOR = "en-GB-SoniaNeural"
MIA = "en-US-JennyNeural"
MAX_V = "en-US-GuyNeural"
PRESENTER = "en-US-AriaNeural"

# (start_s, voice, text, gain, rate)
LINES = [
    (1.3, NARRATOR, "Meetings evaporate. Yours won't.", 1.0, "-4%"),
    (5.7, NARRATOR,
     "meetgraph hosts your calls on your own servers — every speaker captured on their own track.", 1.0, "+4%"),
    (12.1, MIA, "I'm moving the launch to September 17th.", 0.9, "+4%"),
    (15.3, MAX_V, "Payment gateway done by August 30th.", 0.9, "+4%"),
    (17.7, NARRATOR,
     "cognee turns every meeting into a knowledge graph. Decisions, owners, deadlines — linked.", 1.0, "+6%"),
    (25.2, NARRATOR,
     "Ask anything, and get answers with receipts — cited to the exact moment.", 1.0, "+2%"),
    (29.9, PRESENTER, "Presenting from the knowledge graph.", 0.85, "+4%"),
    (32.2, NARRATOR, "meetgraph. Self-hosted meeting intelligence, built on cognee.", 1.0, "+6%"),
]


async def tts(text: str, voice: str, rate: str = "-4%") -> np.ndarray:
    import edge_tts

    buf = io.BytesIO()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    return decode_mono48k(buf)


def decode_mono48k(buf) -> np.ndarray:
    import av

    out = []
    with av.open(buf) as c:
        rs = av.AudioResampler(format="fltp", layout="mono", rate=SR)
        for frame in c.decode(audio=0):
            for rf in rs.resample(frame):
                out.append(rf.to_ndarray()[0])
        for rf in rs.resample(None):
            out.append(rf.to_ndarray()[0])
    return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


# ---------------- SFX synth ----------------

def env(n, a=0.01, r=0.3):
    """attack/release envelope"""
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def pad_bed() -> np.ndarray:
    """soft ambient chord, slow swell, very quiet"""
    t = np.arange(int(DUR * SR)) / SR
    chord = (
        np.sin(2 * np.pi * 110.0 * t)
        + 0.7 * np.sin(2 * np.pi * 164.81 * t)
        + 0.55 * np.sin(2 * np.pi * 220.0 * t)
        + 0.3 * np.sin(2 * np.pi * 329.63 * t)
    )
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t + 1.2)
    bed = chord * lfo
    fade = env(len(bed), a=3.0, r=3.5)
    return (bed * fade * 0.030).astype(np.float32)


def sweep(dur=0.6, k_lo=0.02, k_hi=0.35, gain=0.5, seed=7) -> np.ndarray:
    """filtered-noise sweep; k rising = opening whoosh, falling = closing swipe"""
    n = int(dur * SR)
    noise = np.random.default_rng(seed).standard_normal(n)
    k = np.linspace(k_lo, k_hi, n)
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += k[i] * (noise[i] - acc)
        y[i] = acc
    return (y * env(n, a=dur * 0.3, r=dur * 0.55) * gain).astype(np.float32)


def sparkle() -> np.ndarray:
    """three quick ascending soft tones — the 'graph' transition"""
    notes = [(523.25, 0.0), (659.25, 0.09), (783.99, 0.18)]
    n = int(0.5 * SR)
    y = np.zeros(n, dtype=np.float32)
    for f, at in notes:
        b = blip(f, 0.16, 0.09)
        i = int(at * SR)
        y[i: i + len(b)] += b
    return y


def tick_train(duration: float, interval=0.055) -> np.ndarray:
    """soft keyboard ticks"""
    n = int(duration * SR)
    y = np.zeros(n)
    rng = np.random.default_rng(3)
    t0 = 0.0
    while t0 < duration - 0.01:
        i = int(t0 * SR)
        ln = int(0.004 * SR)
        y[i:i + ln] += rng.standard_normal(ln) * np.linspace(1, 0, ln)
        t0 += interval * (0.8 + 0.4 * rng.random())
    return (y * 0.10).astype(np.float32)


def blip(freq=740.0, dur=0.12, gain=0.16) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    y = np.sin(2 * np.pi * freq * t) * env(len(t), a=0.004, r=0.09)
    return (y * gain).astype(np.float32)


def chime() -> np.ndarray:
    a = blip(880, 0.22, 0.14)
    b = blip(1318.5, 0.34, 0.12)
    off = int(0.10 * SR)
    y = np.zeros(off + len(b), dtype=np.float32)
    y[: len(a)] += a
    y[off:] += b
    return y


# ---------------- mix ----------------

def place(mix: np.ndarray, clip: np.ndarray, at_s: float, gain: float = 1.0) -> None:
    i = int((at_s + OFFSET) * SR)  # shift onto the video clock
    j = min(len(mix), i + len(clip))
    if i < len(mix):
        mix[i:j] += clip[: j - i] * gain


async def main() -> None:
    mix = np.zeros(int(DUR * SR), dtype=np.float32)
    place(mix, pad_bed(), 0.0)

    # transitions — each scene change gets its own character
    place(mix, sweep(0.6, 0.02, 0.35, 0.5), 4.75)                 # → room: opening whoosh
    place(mix, sweep(0.45, 0.30, 0.04, 0.42, seed=11), 10.8)      # → transcript: closing swipe
    place(mix, sparkle(), 16.9)                                    # → graph: ascending tones
    place(mix, sweep(0.32, 0.12, 0.5, 0.3, seed=23), 22.85)       # → ask: short airy swish
    place(mix, blip(987.77, 0.2, 0.13), 29.45)                    # → presenter: join tone only

    place(mix, tick_train(2.2), 12.2)   # Mia's line typing
    place(mix, tick_train(1.9), 14.8)   # Max's line typing
    place(mix, tick_train(1.7), 23.8)   # query typing

    for at, f in ((17.6, 660), (18.4, 740), (18.9, 830), (19.4, 620), (19.9, 700)):
        place(mix, blip(f), at)          # graph nodes pop
    place(mix, chime(), 25.9)            # answer lands

    print("synthesizing voices...")
    for at, voice, text, gain, rate in LINES:
        clip = await tts(text, voice, rate)
        end = at + len(clip) / SR
        print(f"  {voice.split('-')[2][:8]:<9} @{at:>5.1f}s  {len(clip)/SR:4.1f}s  ends {end:5.1f}  {text[:44]}")
        if end > DUR:
            print(f"    !! clips past video end by {end - DUR:.1f}s")
        place(mix, clip, at, gain * 0.9)

    peak = np.max(np.abs(mix))
    if peak > 0:
        mix *= 0.89 / peak

    print("muxing...")
    import av

    with av.open(str(VIDEO_IN)) as inp, av.open(str(VIDEO_OUT), "w") as outp:
        in_v = inp.streams.video[0]
        out_v = outp.add_stream_from_template(in_v)
        out_a = outp.add_stream("libopus", rate=SR)
        out_a.bit_rate = 96_000

        # audio first: encode whole track
        import av.audio.frame as afr

        frame_len = 960  # 20ms @48k
        pts = 0
        audio_packets = []
        for off in range(0, len(mix), frame_len):
            chunk = mix[off: off + frame_len]
            if len(chunk) < frame_len:
                chunk = np.pad(chunk, (0, frame_len - len(chunk)))
            fr = afr.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="flt", layout="mono")
            fr.sample_rate = SR
            fr.pts = pts
            pts += frame_len
            audio_packets.extend(out_a.encode(fr))
        audio_packets.extend(out_a.encode(None))

        video_packets = [p for p in inp.demux(in_v) if p.dts is not None]

        # interleave by presentation time so players/seek behave
        def key(p):
            return float(p.dts * p.time_base)

        for p in audio_packets:
            p.stream = out_a
        for p in video_packets:
            p.stream = out_v
        for p in sorted(audio_packets + video_packets, key=key):
            outp.mux(p)

    print(f"done: {VIDEO_OUT} ({VIDEO_OUT.stat().st_size/1e6:.1f} MB)")


asyncio.run(main())
