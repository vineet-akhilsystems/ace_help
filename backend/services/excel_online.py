"""The shared OneDrive workbook, driven in a hidden Chrome: download it to read, type ticket numbers to write.

Writing only ever types into one empty cell after re-reading the row's identifying cells, so a row that someone
moved, edited or already numbered is never overwritten.
"""
import asyncio
from pathlib import Path
from backend.config import setting

FRAME = 'WacFrame_Excel_0'
NAME_BOX = '#FormulaBar-NameBox-input'
FORMULA = '#formulaBarTextDivId'


def same(a, b):
    return ' '.join(str(a or '').split()).casefold() == ' '.join(str(b or '').split()).casefold()


class ExcelOnline:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.driver = self.browser = None

    async def _browser(self):
        if not (self.browser and self.browser.is_connected()):
            from playwright.async_api import async_playwright
            if not self.driver:
                self.driver = await async_playwright().start()
            self.browser = await self.driver.chromium.launch(headless=True, channel=setting('ACE_BROWSER_CHANNEL', 'chrome') or None)
        return self.browser

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.driver:
            await self.driver.stop()

    async def download(self, url):
        """The workbook as bytes, fetched through the sharing link in a browser session."""
        async with self.lock:
            context = await (await self._browser()).new_context(accept_downloads=True)
            try:
                page = await context.new_page()
                async with page.expect_download(timeout=120000) as info:
                    try:
                        await page.goto(url + ('&' if '?' in url else '?') + 'download=1', timeout=120000)
                    except Exception as exc:  # Chrome reports the navigation as aborted because it became a download
                        if 'Download is starting' not in str(exc):
                            raise
                download = await info.value
                return Path(await download.path()).read_bytes()
            finally:
                await context.close()

    async def write(self, url, tab, writes):
        """writes: [{'cell': 'K11', 'value': 'ASPL-1', 'checks': {'D11': 'text', 'G11': 'Naman Thapa'}}].
        Returns one {'cell', 'status': written|already|changed|hidden|occupied|failed, 'detail'} per write."""
        async with self.lock:
            context = await (await self._browser()).new_context(viewport={'width': 1500, 'height': 900})
            try:
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=120000)
                frame = await self._frame(page)
                results = [await self._write_one(page, frame, tab, w) for w in writes]
                await self._wait_saved(page, frame)
                return results
            finally:
                await context.close()

    async def _frame(self, page):
        for _ in range(240):
            frame = next((f for f in page.frames if f.name == FRAME), None)
            if frame and await frame.locator(NAME_BOX).count() and await frame.locator(FORMULA).count():
                await page.wait_for_timeout(2000)
                return frame
            await page.wait_for_timeout(500)
        raise RuntimeError('Excel Online did not open the workbook for editing.')

    async def _go(self, page, frame, ref):
        """Selects one cell; only returns once the Name Box shows it, so nothing is read or typed elsewhere."""
        box, cell = frame.locator(NAME_BOX), ref.split('!')[-1].upper()
        for _ in range(3):
            await box.click()
            await box.fill(ref)
            await box.press('Enter')
            for _ in range(20):
                await page.wait_for_timeout(250)
                if (await box.input_value()).strip().upper() == cell:
                    await page.wait_for_timeout(300)
                    return
        raise RuntimeError(f'Excel Online did not go to {cell}.')

    async def _read(self, page, frame, ref):
        await self._go(page, frame, ref)
        return (await frame.locator(FORMULA).first.inner_text()).strip()

    async def _read_until(self, page, frame, ref, ok, tries=7):
        """Excel Online's formula bar can lag behind (right after opening, or after typing), so a value that is not
        the expected one is read again for a few seconds before anything is decided on it."""
        value = await self._read(page, frame, ref)
        for _ in range(tries - 1):
            if ok(value):
                break
            await page.wait_for_timeout(700)
            value = await self._read(page, frame, ref)
        return value

    async def _write_one(self, page, frame, tab, w):
        ref = lambda cell: f"'{tab}'!{cell}"  # noqa: E731
        try:
            for cell, expected in w['checks'].items():
                actual = await self._read_until(page, frame, ref(cell), lambda v, e=expected: same(v, e))
                if not actual and str(expected or '').strip():
                    # Excel Online does not load rows a filter hides; their cells read empty, so nothing is typed there.
                    row = ''.join(ch for ch in cell if ch.isdigit())
                    return {'cell': w['cell'], 'status': 'hidden',
                            'detail': f'row {row} shows empty in Excel Online, so a filter is probably hiding it; '
                                      'clear the sheet filter'}
                if not same(actual, expected):
                    return {'cell': w['cell'], 'status': 'changed',
                            'detail': f'{cell} now reads "{actual[:60]}" instead of "{str(expected)[:60]}"'}
            current = await self._read_until(page, frame, ref(w['cell']), lambda v: not v or same(v, w['value']))
            if same(current, w['value']):
                return {'cell': w['cell'], 'status': 'already', 'detail': 'The number was already there.'}
            if current:
                return {'cell': w['cell'], 'status': 'occupied', 'detail': f'{w["cell"]} already holds "{current[:40]}".'}
            if (await frame.locator(NAME_BOX).input_value()).strip().upper() != w['cell'].upper():
                return {'cell': w['cell'], 'status': 'failed', 'detail': f'Excel Online moved away from {w["cell"]}.'}
            await page.keyboard.type(w['value'])
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(700)
            after = await self._read_until(page, frame, ref(w['cell']), lambda v: same(v, w['value']))
            if same(after, w['value']):
                return {'cell': w['cell'], 'status': 'written', 'detail': ''}
            return {'cell': w['cell'], 'status': 'failed', 'detail': f'{w["cell"]} reads "{after[:40]}" after typing.'}
        except Exception as exc:  # one bad cell must not stop the others
            return {'cell': w['cell'], 'status': 'failed', 'detail': str(exc)[:200]}

    async def _wait_saved(self, page, frame):
        # Excel Online saves on its own; give it time and wait until it no longer says "Saving".
        await page.wait_for_timeout(3000)
        for _ in range(40):
            if not await frame.locator('[aria-label^="Saving"]').count():
                return
            await page.wait_for_timeout(500)
