"""HTML → PDF rendering via headless Chromium (Playwright).

Produces a single, wide, flawless-vector PDF from the self-contained dashboard
HTML the service already generates. SVG charts stay vector, text stays
selectable, and background colours are preserved. Chromium is baked into the
Docker image at build time (see Dockerfile), so there is no runtime install.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Fixed wide width keeps the dashboard's multi-column layout from collapsing
# (its CSS collapses below 900px).
DEFAULT_PAGE_WIDTH_PX = 1440

# Max height for a single page (also the per-page height when paginating). A
# default view at/under this is ONE wide page (predictive / target_layout.png).
# Above it, content flows across pages of THIS SAME height, so page count grows
# gradually — just over the limit → 2 pages, not a jump (≤12k=1, ≤24k=2, ≤36k=3).
# Kept below the PDF/Chromium tall-page limit so each page renders cleanly.
SINGLE_PAGE_MAX_HEIGHT_PX = 12000

# Hard ceiling on the whole render. Nothing can hang past this — on timeout we
# tear down the browser and raise, so the request fails cleanly instead of
# spinning forever.
RENDER_TIMEOUT_S = 90

# Force background colours to print. We deliberately do NOT expand inner scroll
# panes — the PDF mirrors the default on-screen view (capped panes), so it stays
# one compact wide page instead of unrolling every hidden row.
_COLOR_CSS = "*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;}"

# TL-7.7 (brief §44): "Do not make dashboard transparent but PDF reports
# absolute." A static PDF has no `:hover` state and no click handlers, so
# two trust-layer affordances that depend on interaction would otherwise
# vanish silently on export:
#   - `title=` tooltips (TL-7.1 badges, TL-7.2's project-trust summary,
#     TL-7.3 evidence chips) — never shown without a mouse hovering.
#   - `.ni-why-panel[hidden]` disclosure panels (TL-7.5's "Why?" buttons)
#     — collapsed by default, only opened by an `onclick` a PDF can't fire.
# Scoped to the specific trust-layer classes that carry a tooltip, not a
# blanket `[title]::after` rule — the dashboard also has non-trust
# `title` attributes (e.g. the changed-rows expand/collapse button) that
# must not sprout unwanted parenthetical text in the exported PDF.
_PDF_TRUST_FALLBACK_CSS = (
    ".ni-why-panel[hidden]{display:block!important;}"
    ".ni-trust-badge[title]::after,"
    ".ni-evidence-label[title]::after,"
    ".ni-trust-summary[title]::after"
    "{content:' (' attr(title) ')';font-weight:400;font-style:italic;}"
)


async def _block_external(route):
    """Abort any external (http/https) subresource so a slow/blocked CDN — e.g.
    the v5 health dashboard's Google Fonts @import — can never stall the render.
    Inline data:/blob: resources are allowed through. Web fonts simply fall back
    to system fonts, instantly."""
    url = route.request.url
    if url.startswith("http://") or url.startswith("https://"):
        await route.abort()
    else:
        await route.continue_()


async def _render(html: str, page_width_px: int) -> bytes:
    from playwright.async_api import async_playwright

    logger.info("pdf: launching chromium")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page(viewport={"width": page_width_px, "height": 1200})
            await page.route("**/*", _block_external)
            await page.emulate_media(media="screen")

            logger.info("pdf: setting content (%d chars)", len(html))
            await page.set_content(html, wait_until="domcontentloaded", timeout=15000)

            # Let on-load JS (the v5 dashboard renders its charts on
            # DOMContentLoaded) and layout settle. Fonts are already resolved
            # since external requests are blocked.
            await page.wait_for_timeout(500)
            await page.add_style_tag(content=_COLOR_CSS)
            # TL-7.7: reveal hover-only trust content as static print text
            # before the page is measured/captured — must land before the
            # height measurement below, since forcing `.ni-why-panel`
            # visible can grow the page's scroll height.
            await page.add_style_tag(content=_PDF_TRUST_FALLBACK_CSS)
            await page.wait_for_timeout(150)

            # Measure the default on-screen height (scroll panes stay capped).
            height_px = int(await page.evaluate(
                "() => Math.max(document.documentElement.scrollHeight,"
                " document.body ? document.body.scrollHeight : 0, 1)"
            ))

            # One wide page if it fits; paginate only as a last resort (a default
            # view that's still enormous — rare).
            if height_px <= SINGLE_PAGE_MAX_HEIGHT_PX:
                page_height = height_px
                logger.info("pdf: height=%spx → single wide page", height_px)
            else:
                page_height = SINGLE_PAGE_MAX_HEIGHT_PX
                pages = -(-height_px // page_height)  # ceil
                logger.info("pdf: height=%spx → paginating into ~%d pages", height_px, pages)

            pdf_bytes = await page.pdf(
                width=f"{page_width_px}px",
                height=f"{page_height}px",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=False,
            )
            logger.info("pdf: done, %d bytes", len(pdf_bytes))
            return pdf_bytes
        finally:
            await browser.close()


async def html_to_pdf(html: str, page_width_px: int = DEFAULT_PAGE_WIDTH_PX) -> bytes:
    """Render `html` to a single wide-page PDF and return the bytes.

    Guaranteed to either return PDF bytes or raise within RENDER_TIMEOUT_S — it
    cannot hang indefinitely.
    """
    if not html or not isinstance(html, str):
        raise ValueError("html_to_pdf requires non-empty HTML")
    try:
        return await asyncio.wait_for(_render(html, page_width_px), timeout=RENDER_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.error("pdf: render exceeded %ss — aborting", RENDER_TIMEOUT_S)
        raise RuntimeError(f"PDF render timed out after {RENDER_TIMEOUT_S}s")
