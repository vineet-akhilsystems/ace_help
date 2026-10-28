import asyncio
import re
from urllib.parse import urlparse
from backend.config import RUNTIME, setting


class PortalError(RuntimeError):
    pass


SLOW_PAGE = 45000  # ms allowed for an ACE document to arrive


class Session:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.driver = self.browser = self.context = None
        self.reader = self.reader_context = self.background_page = None
        self.base = setting('ACE_BASE_URL', 'http://ace.akhilsystems.com', 'BASE_URL').rstrip('/')
        if urlparse(self.base).hostname != 'ace.akhilsystems.com':
            raise ValueError('ACE_BASE_URL must point to ace.akhilsystems.com.')

    async def start(self):
        if self.browser and self.browser.is_connected():
            return
        self.browser, self.context = await self.launch(headless=False)

    async def launch(self, headless):
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            if 'Application Control policy' in str(exc):
                raise PortalError(
                    'Windows Application Control blocked the Playwright greenlet DLL. '
                    'Planning is available, but ACE browser actions require your IT administrator '
                    'to allow the installed Python/greenlet package.'
                ) from exc
            raise
        if not self.driver:
            self.driver = await async_playwright().start()
        # Use the system-installed Chrome/Edge by default. On machines with a Windows
        # Application Control policy (Smart App Control / WDAC / AppLocker), Playwright's
        # own downloaded Chromium is blocked ("spawn UNKNOWN"), while an installed,
        # signed browser is allow-listed. Set ACE_BROWSER_CHANNEL='' to use bundled Chromium.
        channel = setting('ACE_BROWSER_CHANNEL', 'chrome')
        kind = 'hidden reader' if headless else 'browser'
        print(f"[ACE Assistant] [BROWSER] Launching {kind} (channel={channel or 'bundled chromium'})...", flush=True)
        browser = await self.driver.chromium.launch(
            headless=headless,
            channel=channel or None,
            args=[] if headless else ['--start-maximized']
        )
        state = RUNTIME / 'storage_state.json'
        context = await browser.new_context(
            storage_state=str(state) if state.exists() else None,
            timezone_id='Asia/Kolkata', viewport={'width': 1500, 'height': 950})
        context.set_default_timeout(15000)
        return browser, context

    async def close(self):
        if self.context:
            await self.context.close()
        if self.driver:
            await self.driver.stop()

    async def is_login(self, page):
        return await page.locator('input[type=password]').count() > 0

    async def login(self, page):
        username = setting('ACE_USERNAME', legacy='USERNAME')
        password = setting('ACE_PASSWORD', legacy='PASSWORD')
        if not username or not password:
            raise PortalError('Set ACE_USERNAME and ACE_PASSWORD in .env, or sign in in the opened ACE browser.')
        user_selector = setting('ACE_USERNAME_SELECTOR') or '#txtUserID'
        pass_selector = setting('ACE_PASSWORD_SELECTOR') or '#txtPassword'
        button_selector = setting('ACE_LOGIN_SELECTOR') or '#btnLogin'
        # ACE presents the login form twice: the first submit returns to the same
        # login screen (e.g. Online Bug Tracker entry), and a second submit signs in.
        # Submit credentials up to 3 rounds until the password field disappears.
        for _ in range(3):
            if not await self.is_login(page):
                break
            user = page.locator(user_selector)
            secret = page.locator(pass_selector)
            button = page.locator(button_selector)
            if await user.count() != 1 or await secret.count() != 1 or await button.count() != 1:
                raise PortalError('Login controls are unavailable. Sign in in the opened browser and retry.')
            await user.fill(username)
            await secret.fill(password)
            async with page.expect_navigation(wait_until='domcontentloaded', timeout=SLOW_PAGE):
                await button.click()
        if await self.is_login(page):
            raise PortalError('ACE login did not complete. Check credentials or finish login in the browser.')
        await page.context.storage_state(path=str(RUNTIME / 'storage_state.json'))

    async def background(self, path):
        # Status checks and ticket reads use one reusable page in a second, headless
        # Chrome. As a visible tab it sat beside the draft showing the same date with
        # an empty grid, which looked like a second, failed fill.
        if not (self.reader and self.reader.is_connected()):
            self.reader, self.reader_context = await self.launch(headless=True)
        page = self.background_page
        if page is None or page.is_closed():
            page = self.background_page = await self.reader_context.new_page()
        return await self.goto(page, path)

    async def open(self, path):
        await self.start()
        print(f"[ACE Assistant] [TAB] Opening new ACE tab for {path}", flush=True)
        return await self.goto(await self.context.new_page(), path)

    async def goto(self, page, path):
        await self.navigate(page, path)
        if await self.is_login(page):
            await self.login(page)
            await self.navigate(page, path)
        if await self.is_login(page):
            raise PortalError('ACE session expired. Sign in and retry.')
        return page

    async def navigate(self, page, path):
        # ACE's login page can take longer than the 15s default (its background image
        # alone stalls), so wait only for the document there; a signed-in page loads
        # fast and is allowed to settle fully.
        await page.goto(self.base + path, wait_until='domcontentloaded', timeout=SLOW_PAGE)
        if not await self.is_login(page):
            await page.wait_for_load_state('networkidle')
