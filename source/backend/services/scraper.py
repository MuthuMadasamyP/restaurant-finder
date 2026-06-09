"""
Playwright-based restaurant scraper targeting Google Maps.

Root-cause fix (v2):
  Previous version used element references (link.click()) which became STALE
  after page navigation, causing the same restaurant to be clicked 2-3 times
  and producing duplicates + "Results" false-positives.

  v2 collects all place HREF strings first, then navigates via page.goto() —
  no element references survive across page loads, zero stale-element issues.

Changes in v2:
  - href-based navigation (page.goto) instead of link.click() + go_back()
  - Address-level deduplication (catches same restaurant with 2 Google listings)
  - Stricter junk-name detection (exact + substring matching)
  - Longer settling wait after page load for reliable h1 extraction
  - More aggressive scrolling (6 passes) to surface 15+ results
  - Increased candidate limit to 30 to reliably reach 10 valid restaurants
"""

import asyncio
import logging
import os
import re
import sys
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from playwright.async_api import (
    Page,
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)

# ── Timing constants ──────────────────────────────────────────────────────────
TIMEOUT      = 5_000    # ms - element wait timeout
NAV_TIMEOUT  = 12_000   # ms - page navigation timeout
SETTLE_WAIT  = 0.7      # s  - wait after navigation for content to stabilise

# ── Junk-name filters ─────────────────────────────────────────────────────────
# Exact matches (after lowercase + strip)
JUNK_NAMES_EXACT: set[str] = {
    "results", "more results", "see more results", "all results",
    "open in google maps", "back to results", "search nearby",
    "save", "directions", "nearby", "all filters", "open now",
    "top rated", "price", "type", "sponsored", "ad",
    "suggest an edit", "add a photo", "share", "send to phone",
    "overview", "reviews", "photos", "menu", "about",
}
# Substring matches — if name CONTAINS any of these, reject it
JUNK_SUBSTRINGS: tuple[str, ...] = (
    "open in google",
    "get directions",
    "more photos",
    "add missing",
    "suggest an",
)

# ── CSS selector maps (ordered: most-likely → fallback) ──────────────────────
SEL_FEED = ['div[role="feed"]', '.m6QErb[aria-label]', 'div.m6QErb']

SEL_RESULT_LINKS = [
    "a.hfpxzc",
    "a.hfpxzc[href*='/maps/place/']",
    "div[role='feed'] a[href*='maps/place']",
    "[data-result-index] a",
]

SEL_NAME = [
    "h1.DUwDvf",
    'h1[class*="fontHeadlineLarge"]',
    "h1",
]

SEL_RATING = [
    "div.F7nice > span > span[aria-hidden='true']",
    "span.MW4etd",
    "div.UY7F9 span[aria-hidden='true']",
    "span.ceNzKf",
]

SEL_ADDRESS = [
    "button[data-item-id='address']",
    "[data-tooltip='Copy address'] button",
    "button.CsEnBe[data-item-id='address']",
    "div[data-id='address']",
]

SEL_PHONE = [
    "button[data-item-id*='phone:tel']",
    "button[data-tooltip*='phone'] span.Io6YTe",
    "button[data-item-id*='pn:'] span.Io6YTe",
    "[aria-label*='Phone'] span",
]

SEL_CATEGORY = [
    "button.DkEaL",
    "span.YhemCb",
    "button.skqShb",
    "div.LBgpqf button",
]

SEL_WEBSITE = [
    "a[data-item-id='authority']",
    "a[data-tooltip='Open website']",
    "a[aria-label*='Website']",
    "a[href^='http']:has(span.Io6YTe)",
]


# ── Public entry point ────────────────────────────────────────────────────────

async def scrape_restaurants(location: str, radius_km: float, max_results: int = 10) -> list[dict]:
    """
    Scrape restaurants from Google Maps for the given location.

    Returns:
        Up to max_results unique restaurant dicts, sorted by rating DESC.
        Keys: name, rating, address, phone, category, website
    """
    results: list[dict] = []
    max_results = max(1, min(int(max_results or 10), 10))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--mute-audio",
                "--no-zygote",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1024,720",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1024, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = await context.new_page()
        await page.route("**/*", _block_heavy_assets)
        try:
            results = await _do_scrape(page, location, radius_km, max_results)
        except Exception as exc:
            logger.error("Scraping session crashed: %s", exc, exc_info=True)
        finally:
            await browser.close()

    results.sort(key=_numeric_rating, reverse=True)
    return results[:max_results]


async def scrape_restaurants_threaded(location: str, radius_km: float, max_results: int = 10) -> list[dict]:
    """Run Playwright in a worker thread with a subprocess-capable loop on Windows."""
    return await asyncio.to_thread(_scrape_restaurants_sync, location, radius_km, max_results)


async def scrape_restaurant_detail_threaded(maps_url: str) -> Optional[dict]:
    """Fetch one Google Maps detail page in a worker thread."""
    return await asyncio.to_thread(_scrape_restaurant_detail_sync, maps_url)


def _scrape_restaurants_sync(location: str, radius_km: float, max_results: int = 10) -> list[dict]:
    if sys.platform.startswith("win") and hasattr(asyncio, "ProactorEventLoop"):
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(scrape_restaurants(location, radius_km, max_results))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    return asyncio.run(scrape_restaurants(location, radius_km, max_results))


# ── Core scraping logic ───────────────────────────────────────────────────────

def _scrape_restaurant_detail_sync(maps_url: str) -> Optional[dict]:
    if sys.platform.startswith("win") and hasattr(asyncio, "ProactorEventLoop"):
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(scrape_restaurant_detail(maps_url))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    return asyncio.run(scrape_restaurant_detail(maps_url))


async def scrape_restaurant_detail(maps_url: str) -> Optional[dict]:
    if not maps_url.startswith(("https://www.google.", "https://google.")):
        raise ValueError("Only Google Maps detail URLs are supported.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--mute-audio",
                "--no-zygote",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1024,720",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1024, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()
        await page.route("**/*", _block_heavy_assets)
        try:
            detail = await _extract_restaurant_from_url(page, maps_url)
            if detail:
                detail["maps_url"] = maps_url
            return detail
        finally:
            await browser.close()


async def _do_scrape(page: Page, location: str, radius_km: float, max_results: int) -> list[dict]:
    """
    Step 1: Load the search results page and collect place URLs.
    Step 2: Visit each place URL directly (no stale element risk).
    Step 3: Filter + deduplicate, return up to max_results valid restaurants.
    """
    search_url = (
        f"https://www.google.com/maps/search/"
        f"restaurants+near+{location.replace(' ', '+')}"
        f"?hl=en"
    )
    logger.info("Loading search page → %s", search_url)
    await page.goto(search_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    await _dismiss_dialogs(page)

    # Wait for the results feed
    feed_loaded = False
    for sel in SEL_FEED:
        try:
            await page.wait_for_selector(sel, timeout=TIMEOUT)
            feed_loaded = True
            logger.info("Feed confirmed via: %s", sel)
            break
        except PlaywrightTimeoutError:
            continue

    if not feed_loaded:
        logger.warning("Results feed not found — page structure may have changed")
        return []

    await asyncio.sleep(1)
    scroll_passes = min(5, max(3, (max_results // 5) + 2))
    await _scroll_feed(page, passes=scroll_passes)

    # ── COLLECT HREFS (not element references) ────────────────────────────────
    # This is the key v2 fix: store the URL strings, not DOM element handles.
    # Element handles become stale after navigation; strings never do.
    place_hrefs: list[str] = []
    for sel in SEL_RESULT_LINKS:
        links = await page.query_selector_all(sel)
        if not links:
            continue
        for link in links:
            href = await link.get_attribute("href")
            if not href:
                continue
            # Normalise to absolute URL
            if href.startswith("/"):
                href = f"https://www.google.com{href}"
            # Must be a Google Maps place page
            if "/maps/place/" not in href:
                continue
            # Deduplicate URLs themselves
            if href not in place_hrefs:
                place_hrefs.append(href)
        if place_hrefs:
            logger.info("Collected %d place URLs via: %s", len(place_hrefs), sel)
            break

    if not place_hrefs:
        logger.warning("No place URLs found in the feed")
        return []

    # ── VISIT EACH PLACE PAGE ─────────────────────────────────────────────────
    full_details = os.getenv("SCRAPER_MODE", "fast").strip().lower() == "full"
    fast_results = [] if full_details else await _extract_restaurants_from_cards(page, max_results)
    if fast_results:
        logger.info("Collected %d fast card results", len(fast_results))
        enriched_results = await _enrich_fast_results(page, fast_results, place_hrefs)
        return enriched_results[:max_results]

    restaurants: list[dict] = []
    seen_names: set[str]    = set()     # normalised name keys
    seen_addrs: set[str]    = set()     # normalised address keys (catches duplicates with same address)

    candidate_limit = min(len(place_hrefs), max_results + 4)
    for idx, href in enumerate(place_hrefs[:candidate_limit]):
        if len(restaurants) >= max_results:
            break

        logger.info("Processing [%d/%d]", idx + 1, candidate_limit)
        try:
            data = await _extract_restaurant_from_url(page, href)
        except Exception as exc:
            logger.warning("  Extraction error: %s", exc)
            continue

        if not data or not data.get("name"):
            continue

        # ── Filter: reject Google Maps UI junk ──────────────────────────────
        name_lower = data["name"].strip().lower()
        if len(name_lower) < 3:
            logger.debug("  ✗ Too short: %r", data["name"])
            continue
        if name_lower in JUNK_NAMES_EXACT:
            logger.debug("  ✗ Exact junk: %r", data["name"])
            continue
        if any(sub in name_lower for sub in JUNK_SUBSTRINGS):
            logger.debug("  ✗ Substring junk: %r", data["name"])
            continue

        # ── Dedup: by normalised name ────────────────────────────────────────
        name_key = re.sub(r"[^a-z0-9]", "", name_lower)
        if name_key in seen_names:
            logger.debug("  ✗ Duplicate name: %r", data["name"])
            continue

        # ── Dedup: by address (same location, different listing) ─────────────
        addr = data.get("address", "N/A")
        if addr and addr != "N/A":
            addr_key = re.sub(r"\s+", " ", addr.lower().strip())[:100]
            if addr_key in seen_addrs:
                logger.debug("  ✗ Duplicate address: %r", addr)
                continue
            seen_addrs.add(addr_key)

        seen_names.add(name_key)
        restaurants.append(data)
        logger.info("  ✓ [%d] %-35s ★%s", len(restaurants), data["name"], data.get("rating", "?"))

    return restaurants


async def _extract_restaurants_from_cards(page: Page, max_results: int) -> list[dict]:
    """Fast Render-friendly extraction from the search result cards."""
    try:
        cards = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll("a.hfpxzc[href*='/maps/place/']")).map((anchor) => {
                const card = anchor.closest(".Nv2PK, [role='article'], div");
                return {
                    name: anchor.getAttribute("aria-label") || anchor.textContent || "",
                    href: anchor.href || "",
                    text: card ? card.innerText || "" : ""
                };
            })
            """
        )
    except Exception as exc:
        logger.warning("Fast card extraction failed: %s", exc)
        return []

    restaurants: list[dict] = []
    seen_names: set[str] = set()
    for card in cards:
        name = _clean_text(str(card.get("name") or ""))
        name_key = re.sub(r"[^a-z0-9]", "", name.lower())
        if not name_key or name_key in seen_names:
            continue
        if name.lower() in JUNK_NAMES_EXACT or any(sub in name.lower() for sub in JUNK_SUBSTRINGS):
            continue

        text = _clean_text(str(card.get("text") or ""))
        rating_match = re.search(r"\b([1-5](?:[.,]\d)?)\b", text)
        rating = rating_match.group(1).replace(",", ".") if rating_match else "N/A"

        category = "N/A"
        parts = [part.strip() for part in re.split(r"[\n·]", text) if part.strip()]
        for part in parts:
            lower = part.lower()
            if part == name or re.search(r"\d", part):
                continue
            if any(word in lower for word in ("restaurant", "hotel", "cafe", "biryani", "food")):
                category = _clean_text(part)
                break

        seen_names.add(name_key)
        restaurants.append(
            {
                "name": name,
                "rating": rating,
                "address": "N/A",
                "phone": "N/A",
                "category": category,
                "website": _normalise_website_url(card.get("href")),
                "maps_url": card.get("href") or "N/A",
            }
        )
        if len(restaurants) >= max_results:
            break

    return restaurants


async def _enrich_fast_results(
    page: Page,
    restaurants: list[dict],
    place_hrefs: list[str],
) -> list[dict]:
    """Add detail-page fields for the first few rows without timing out free hosting."""
    enrich_limit = min(_detail_enrich_limit(), len(restaurants), len(place_hrefs))
    if enrich_limit <= 0:
        return restaurants

    for index in range(enrich_limit):
        try:
            detail = await _extract_restaurant_from_url(page, place_hrefs[index])
        except Exception as exc:
            logger.warning("Fast result enrichment failed [%d]: %s", index + 1, exc)
            continue

        if not detail:
            continue

        for key in ("address", "phone", "category", "website"):
            value = detail.get(key)
            if value and value != "N/A":
                restaurants[index][key] = value

        if detail.get("rating") and detail["rating"] != "N/A":
            restaurants[index]["rating"] = detail["rating"]

    return restaurants


def _detail_enrich_limit() -> int:
    try:
        return max(0, min(int(os.getenv("DETAIL_ENRICH_LIMIT", "0")), 10))
    except ValueError:
        return 0


async def _block_heavy_assets(route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        await route.abort()
        return
    await route.continue_()


async def _extract_restaurant_from_url(page: Page, url: str) -> Optional[dict]:
    """
    Navigate directly to a restaurant's Google Maps page and extract its details.
    Using goto() instead of click() avoids all stale-element-reference issues.
    """
    await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    # Wait for h1 AND give it extra time to stabilise.
    # Without the extra sleep, h1 sometimes still shows transitional text.
    try:
        await page.wait_for_selector("h1", timeout=TIMEOUT)
        await asyncio.sleep(SETTLE_WAIT)     # <── critical: let dynamic content settle
    except PlaywrightTimeoutError:
        logger.debug("h1 timeout at %s", url)
        return None

    rest: dict = {}

    # Name
    rest["name"] = await _safe_text(page, SEL_NAME)

    # Rating — normalise to numeric string "4.3"
    raw_rating = await _safe_text(page, SEL_RATING)
    if raw_rating and raw_rating != "N/A":
        m = re.search(r"(\d+[.,]\d+|\d+)", raw_rating)
        rest["rating"] = m.group(1).replace(",", ".") if m else raw_rating
    else:
        rest["rating"] = "N/A"

    # Address
    rest["address"] = await _safe_text(page, SEL_ADDRESS)

    # Phone
    rest["phone"] = await _safe_text(page, SEL_PHONE)

    # Category / cuisine type
    rest["category"] = await _safe_text(page, SEL_CATEGORY)

    # Official website, when Google Maps exposes one
    rest["website"] = await _safe_href(page, SEL_WEBSITE)

    return rest if rest.get("name") and rest["name"] != "N/A" else None


# ── Utility helpers ───────────────────────────────────────────────────────────

async def _safe_text(page: Page, selectors: list[str]) -> str:
    """Try each CSS selector in order; return first non-empty text found."""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = await el.text_content()
                if text and text.strip():
                    return _clean_text(text)
        except Exception:
            continue
    return "N/A"


async def _safe_href(page: Page, selectors: list[str]) -> str:
    """Try each CSS selector in order; return the first usable external URL."""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue
            href = await el.get_attribute("href")
            website = _normalise_website_url(href)
            if website != "N/A":
                return website

            aria = await el.get_attribute("aria-label")
            website = _normalise_website_url(aria)
            if website != "N/A":
                return website

            text = await el.text_content()
            website = _normalise_website_url(text)
            if website != "N/A":
                return website
        except Exception:
            continue

    try:
        candidates = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a')).map((a) => ({
                href: a.href || '',
                aria: a.getAttribute('aria-label') || '',
                item: a.getAttribute('data-item-id') || '',
                tooltip: a.getAttribute('data-tooltip') || '',
                text: a.textContent || ''
            })).filter((a) => {
                const haystack = `${a.href} ${a.aria} ${a.item} ${a.tooltip} ${a.text}`.toLowerCase();
                return haystack.includes('website') || haystack.includes('authority');
            })
            """
        )
        for candidate in candidates:
            for key in ("href", "aria", "tooltip", "text", "item"):
                website = _normalise_website_url(candidate.get(key))
                if website != "N/A":
                    return website
    except Exception:
        pass

    return "N/A"


def _normalise_website_url(value: Optional[str]) -> str:
    """Convert Google Maps website values into a clean official URL."""
    if not value:
        return "N/A"

    raw = _clean_text(value)
    if raw == "N/A":
        return "N/A"

    raw = raw.replace("Website:", "", 1).strip()
    parsed = urlparse(raw)

    if parsed.netloc and "google." in parsed.netloc:
        params = parse_qs(parsed.query)
        for key in ("q", "url"):
            target = params.get(key, [""])[0]
            if target:
                return _normalise_website_url(unquote(target))
        return "N/A"

    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if any(blocked in parsed.netloc for blocked in ("google.", "gstatic.", "ggpht.")):
            return "N/A"
        return raw

    domain_match = re.search(
        r"((?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9-]+)+)(?:/[^\s]*)?",
        raw,
    )
    if domain_match:
        domain = domain_match.group(0)
        if "google." not in domain:
            return f"https://{domain}"

    return "N/A"


def _clean_text(text: str) -> str:
    """Remove Google Maps icon glyphs and normalize whitespace."""
    cleaned = re.sub(r"[\ue000-\uf8ff]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "N/A"


async def _dismiss_dialogs(page: Page) -> None:
    """Silently dismiss cookie-consent or GDPR dialogs if they appear."""
    for sel in [
        'button[aria-label="Accept all"]',
        'button[aria-label="Reject all"]',
        'button[jsname="b3VHJd"]',
        'form[action*="consent"] button',
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=2_000)
            if btn:
                await btn.click()
                await asyncio.sleep(0.5)
                return
        except PlaywrightTimeoutError:
            continue


async def _scroll_feed(page: Page, passes: int = 6) -> None:
    """Scroll the results feed multiple times to load all lazy-loaded items."""
    for sel in SEL_FEED:
        feed = await page.query_selector(sel)
        if feed:
            for _ in range(passes):
                try:
                    await feed.evaluate("el => el.scrollBy(0, 600)")
                    await asyncio.sleep(0.7)
                except Exception:
                    pass
            logger.info("Scrolled feed %d×", passes)
            return


def _numeric_rating(r: dict) -> float:
    """Parse rating to float for sorting; invalid → 0."""
    try:
        return float(str(r.get("rating", "0")).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0
