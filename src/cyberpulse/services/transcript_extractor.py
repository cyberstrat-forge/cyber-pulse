"""Transcript extraction using Playwright headless browser."""

import logging
from dataclasses import dataclass

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    """Result of transcript extraction.

    Attributes:
        success: Whether transcript was successfully extracted
        text: Full transcript text (success only)
        lines: List of {timestamp, text} dicts (success only)
        error: Error message (failure only)
    """

    success: bool
    text: str | None = None
    lines: list[dict[str, str]] | None = None
    error: str | None = None


class TranscriptExtractor:
    """Extract YouTube video transcripts using Playwright.

    Uses headless browser to bypass YouTube's timedtext API rate limiting.

    Features:
    - Headless mode: No visible browser window
    - Muted audio: No sound during extraction
    - Automatic fallback detection: Handles videos without subtitles

    Example:
        extractor = TranscriptExtractor(headless=True)
        result = await extractor.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        if result.success:
            print(result.text)
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 60,
        user_data_dir: str = "/tmp/playwright_yt_data",
    ):
        """Initialize transcript extractor.

        Args:
            headless: Run browser in headless mode (no window)
            timeout: Page load timeout in seconds
            user_data_dir: Directory for browser profile data
        """
        self.headless = headless
        self.timeout = timeout
        self.user_data_dir = user_data_dir

    async def extract(self, video_url: str) -> TranscriptResult:
        """Extract transcript from a YouTube video.

        Args:
            video_url: Full YouTube video URL

        Returns:
            TranscriptResult with:
            - success: True if transcript extracted
            - text: Full transcript text (success only)
            - lines: List of {timestamp, text} dicts (success only)
            - error: Error message (failure only)
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--mute-audio",
                    "--disable-audio-output",
                ],
            )

            try:
                page = browser.pages[0] if browser.pages else await browser.new_page()

                logger.debug(f"Loading video page: {video_url}")
                await page.goto(
                    video_url, wait_until="networkidle", timeout=self.timeout * 1000
                )
                await page.wait_for_timeout(3000)

                # Scroll to reveal transcript button
                await page.evaluate("window.scrollTo(0, 600)")
                await page.wait_for_timeout(1000)

                # Click transcript button
                clicked = await page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.innerText || '';
                            const label = btn.getAttribute('aria-label') || '';
                            if (text.includes('Show transcript') || label.includes('Show transcript')) {
                                btn.click();
                                return 'clicked';
                            }
                        }
                        return 'not found';
                    }
                """)

                if clicked != "clicked":
                    return TranscriptResult(
                        success=False,
                        error="No transcript button found - video may not have subtitles",
                    )

                await page.wait_for_timeout(5000)

                # Extract transcript from panel
                result = await page.evaluate("""
                    () => {
                        const panel = document.querySelector(
                            'ytd-engagement-panel-section-list-renderer[visibility="ENGAGEMENT_PANEL_VISIBILITY_EXPANDED"]'
                        );
                        if (!panel) return { error: 'No transcript panel' };

                        const text = panel.innerText;
                        if (text.length < 50) return { error: 'Empty transcript' };

                        const lines = [];
                        const parts = text.split('\\n');

                        let currentTimestamp = '';
                        let currentText = '';

                        for (const part of parts) {
                            const p = part.trim();
                            if (!p) continue;
                            if (p === 'Transcript' || p === 'Search transcript') continue;

                            // Match timestamp (e.g., "0:03", "1:23", "10:45")
                            if (/^\\d+:\\d+$/.test(p)) {
                                if (currentText.trim()) {
                                    lines.push({ timestamp: currentTimestamp, text: currentText.trim() });
                                }
                                currentTimestamp = p;
                                currentText = '';
                            } else if (/^\\d+ seconds?$/.test(p) || /^\\d+ minutes?, \\d+ seconds?$/.test(p)) {
                                // Skip duration hints
                                continue;
                            } else {
                                currentText += ' ' + p;
                            }
                        }

                        if (currentText.trim()) {
                            lines.push({ timestamp: currentTimestamp, text: currentText.trim() });
                        }

                        return { lines, rawLength: text.length };
                    }
                """)

                if result.get("error"):
                    return TranscriptResult(success=False, error=result["error"])

                lines = result.get("lines", [])
                if not lines:
                    return TranscriptResult(
                        success=False, error="No transcript lines extracted"
                    )

                full_text = " ".join(line["text"] for line in lines)

                logger.info(
                    f"Extracted {len(lines)} transcript lines, {len(full_text)} chars"
                )

                return TranscriptResult(success=True, text=full_text, lines=lines)

            except Exception as e:
                logger.error(f"Transcript extraction error: {e}")
                return TranscriptResult(success=False, error=str(e))

            finally:
                await browser.close()