"""Capture one Cian search page for inspection; no listing extraction."""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.sync_api import Browser, Error as PlaywrightError, Page, Playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


@dataclass(frozen=True)
class SearchConfig:
    city: str = "Красноярск"
    operation: str = "sale"
    property_type: str = "flat"
    url: str = "https://krasnoyarsk.cian.ru/kupit-kvartiru/"


SEARCH = SearchConfig()
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "cian"
LISTINGS_FILE = RAW_DIR / "listings.json"
NAVIGATION_TIMEOUT_MS = 30_000
LOAD_TIMEOUT_MS = 10_000
logger = logging.getLogger(__name__)


def create_browser(playwright: Playwright) -> Browser:
    return playwright.chromium.launch(headless=False, timeout=NAVIGATION_TIMEOUT_MS)


def open_page(browser: Browser, config: SearchConfig = SEARCH) -> tuple[Page, int | None]:
    """Open the configured Cian page once and report the main response status."""
    hostname = urlparse(config.url).hostname
    if hostname != "cian.ru" and not (hostname and hostname.endswith(".cian.ru")):
        raise ValueError("Only cian.ru URLs are supported")

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        response = page.goto(config.url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        status = response.status if response else None
        try:
            page.wait_for_load_state("load", timeout=LOAD_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            logger.warning("Page load timed out; capturing the current state")
        logger.info("Opened %s (HTTP %s)", page.url, status)
        return page, status
    except PlaywrightTimeoutError:
        logger.warning("Navigation timed out; capturing the current state")
        return page, None
    except Exception:
        page.close()
        raise


def capture_page_state(
    page: Page, http_status: int | None, config: SearchConfig = SEARCH,
    output_dir: Path = RAW_DIR,
) -> dict:
    """Save a screenshot, rendered HTML and timestamped metadata."""
    captured_at = datetime.now(timezone.utc)
    stamp = captured_at.strftime("%Y%m%dT%H%M%S%fZ")
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshots_dir / f"search_{stamp}.png"
    html = output_dir / f"search_{stamp}.html"
    metadata = output_dir / f"search_{stamp}.json"

    html.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(screenshot))
    state = {
        "source": "cian",
        "captured_at": captured_at.isoformat(),
        "search": {
            "city": config.city,
            "operation": config.operation,
            "property_type": config.property_type,
        },
        "requested_url": config.url,
        "page_url": page.url,
        "page_title": page.title(),
        "http_status": http_status,
        "screenshot": str(screenshot.relative_to(output_dir)),
        "html": html.name,
    }
    metadata.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved screenshot: %s", screenshot)
    logger.info("Saved HTML: %s", html)
    logger.info("Saved metadata: %s", metadata)
    return state


def validate_listing(listing: dict) -> bool:
    """Reject records that cannot be tied to a valid Krasnoyarsk sale page."""
    if listing["source"] != "cian" or not listing["parsed_at"]:
        return False
    url = listing["url"]
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or not re.fullmatch(r"/sale/flat/\d+/?", parsed.path):
        return False
    if parsed.hostname != "cian.ru" and not (parsed.hostname and parsed.hostname.endswith(".cian.ru")):
        return False
    id_match = re.fullmatch(r"/sale/flat/(\d+)/?", parsed.path)
    if not id_match or listing["listing_id"] != id_match.group(1):
        return False
    price, area = listing["price"], listing["area"]
    if price is not None and (type(price) not in (int, float) or price < 0):
        return False
    if area is not None and (type(area) not in (int, float) or area <= 0):
        return False
    return listing["city"] == SEARCH.city


def collect_listings(page: Page) -> list[dict]:
    """Read only the search-result cards currently present in the DOM."""
    cards = page.locator('[data-name="CardComponent"]')
    try:
        cards.first.wait_for(state="attached", timeout=LOAD_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.warning("No listing cards appeared within the timeout")
        return []

    parsed_at = datetime.now(timezone.utc).isoformat()
    listings: list[dict] = []
    seen_ids: set[str] = set()
    card_count = cards.count()
    for index in range(card_count):
        card = cards.nth(index)
        title_node = card.locator('[data-mark="OfferTitle"]').first
        price_node = card.locator('[data-mark="MainPrice"]').first
        link_node = card.locator('a[href*="/sale/flat/"]').first
        title = ((title_node.text_content() or "").strip() or None) if title_node.count() else None
        price_text = (price_node.text_content() or "").strip() if price_node.count() else None
        href = link_node.get_attribute("href") if link_node.count() else None
        geo = [text.strip() for text in card.locator('[data-name="GeoLabel"]').all_text_contents() if text.strip()]

        parsed_url = urlparse(urljoin(page.url, href)) if href else None
        url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "", "")) if parsed_url else None
        id_match = re.fullmatch(r"/sale/flat/(\d+)/?", parsed_url.path) if parsed_url else None
        price_match = re.fullmatch(r"([\d\s]+)\s*₽", price_text) if price_text else None
        area_match = re.search(r"(\d+(?:[,.]\d+)?)\s*м²", title) if title else None
        rooms_match = re.search(r"(\d+)-комн", title) if title else None
        floor_match = re.search(r"(\d+)\s*/\s*\d+\s*этаж", title) if title else None

        listing = {
            "listing_id": id_match.group(1) if id_match else None,
            "source": "cian",
            "url": url,
            "title": title,
            "price": int(re.sub(r"\s", "", price_match.group(1))) if price_match else None,
            "rooms": int(rooms_match.group(1)) if rooms_match else None,
            "area": float(area_match.group(1).replace(",", ".")) if area_match else None,
            "floor": int(floor_match.group(1)) if floor_match else None,
            "address": ", ".join(geo) if geo else None,
            "city": SEARCH.city if SEARCH.city in geo else None,
            "parsed_at": parsed_at,
        }
        if not validate_listing(listing):
            logger.warning("Skipped invalid card %s: %s", index + 1, listing["url"])
            continue
        if listing["listing_id"] in seen_ids:
            continue
        seen_ids.add(listing["listing_id"])
        listings.append(listing)

    logger.info("Found %s cards; validated %s listings", card_count, len(listings))
    return listings


def save_raw_data(listings: list[dict], path: Path = LISTINGS_FILE) -> Path:
    """Save validated listings as a JSON array without database writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %s listings to %s", len(listings), path)
    return path


def main() -> int:
    try:
        with sync_playwright() as playwright:
            browser = create_browser(playwright)
            try:
                page, status = open_page(browser)
                state = capture_page_state(page, status)
                expected = (status == 200 and
                            urlparse(state["page_url"]).hostname == "krasnoyarsk.cian.ru" and
                            SEARCH.city.lower() in state["page_title"].lower())
                if not expected:
                    logger.error("Captured page does not match the expected Krasnoyarsk apartment search")
                    return 1
                listings = collect_listings(page)
                if not listings:
                    logger.error("No valid listings found; keeping the previous listings.json")
                    return 1
                save_raw_data(listings)
            finally:
                browser.close()
        return 0
    except (OSError, ValueError, PlaywrightError):
        logger.exception("Could not capture Cian search page")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
