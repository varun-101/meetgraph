"""Record intro.html at 4K: zoom the 1280x720 stage 3x inside a 3840x2160
viewport (native re-render — text and vectors stay crisp)."""
import asyncio
from pathlib import Path

REPO = Path(r"d:\codes\cognee_hackathon\meetgraph")
SRC = REPO / "docs" / "intro" / "intro.html"
OUT_DIR = REPO / "docs" / "intro"
W, H = 3840, 2160
DURATION_S = 37


async def main() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=["--force-device-scale-factor=1", "--disable-gpu-vsync"]
        )
        ctx = await browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(OUT_DIR / "_rec4k"),
            record_video_size={"width": W, "height": H},
        )
        page = await ctx.new_page()
        await page.goto(SRC.as_uri() + "?scale=3")
        await page.wait_for_timeout(DURATION_S * 1000)
        await ctx.close()
        video_path = await page.video.path()
        await browser.close()

    final = OUT_DIR / "intro-4k-silent.webm"
    Path(video_path).replace(final)
    (OUT_DIR / "_rec4k").rmdir()
    print(f"saved: {final} ({final.stat().st_size / 1e6:.1f} MB)")


asyncio.run(main())
