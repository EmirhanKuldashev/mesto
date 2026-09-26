"""Collect public Cian apartment listings and Krasnoyarsk residential complexes."""

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

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
COMPLEXES_FILE = RAW_DIR / "complexes.json"
COMPLEXES_URL = "https://krasnoyarsk.cian.ru/novostroyki/"
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


def collect_complexes(page: Page) -> list[dict]:
    """Extract ЖК links visible on one city search page, without guessing locations."""
    captured_at = datetime.now(timezone.utc).isoformat()
    results = {}
    anchors = page.locator('[data-name="OffersLayout"] a[href]').evaluate_all(
        "nodes => nodes.map(node => ({href: node.href, name: node.textContent.trim(), title: node.title}))"
    )
    for anchor in anchors:
        href = anchor["href"]
        if not href:
            continue
        parsed = urlparse(urljoin(page.url, href))
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host.endswith(".cian.ru"):
            continue
        if not host.startswith("zhk-"):
            continue
        name = (anchor["name"] or anchor["title"] or "").strip()
        if not name or not (name.startswith("ЖК ") or "жилой комплекс" in name.lower()):
            continue
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))
        external_id = host
        results[external_id] = {
            "complex_id": external_id, "source": "cian", "url": url, "name": name,
            "city": SEARCH.city, "address": None,
            "latitude": None, "longitude": None, "price_from": None,
            "parsed_at": captured_at,
        }
    logger.info("Found %s ЖК links on %s", len(results), page.url)
    return list(results.values())


def collect_all_complexes(browser: Browser, *, max_pages: int = 20, delay_seconds: float = 2) -> list[dict]:
    """Walk public search pagination; fail closed on blocks or incomplete traversal."""
    if max_pages < 1 or delay_seconds < 0:
        raise ValueError("Invalid crawl limits")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    seen_pages = set()
    complexes = {}
    next_url = COMPLEXES_URL
    expected_count = None
    try:
        for index in range(max_pages):
            parsed_url = urlparse(next_url)
            if parsed_url.scheme != "https" or parsed_url.hostname != "krasnoyarsk.cian.ru" or parsed_url.path not in ("/novostroyki/", "/newobjects/list"):
                raise ValueError(f"Unexpected pagination URL: {next_url}")
            if parsed_url.path == "/newobjects/list":
                query = parse_qs(parsed_url.query)
                if query.get("region") != ["4827"] or query.get("offer_type") != ["newobject"] or query.get("p") != [str(index + 1)]:
                    raise ValueError(f"Unexpected Cian ЖК pagination parameters: {next_url}")
            if next_url in seen_pages:
                raise ValueError("Cian pagination loop detected")
            seen_pages.add(next_url)
            response = page.goto(next_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            if response is None or response.status != 200:
                raise RuntimeError(f"Cian ЖК search unavailable: HTTP {response.status if response else 'no response'} at {next_url}")
            title = page.title()
            if SEARCH.city.lower() not in title.lower():
                raise ValueError("Cian ЖК page is not the Krasnoyarsk search")
            if expected_count is None:
                match = re.search(r"(\d+)\s+жил", title)
                expected_count = int(match.group(1)) if match else None
            page_records = collect_complexes(page)
            if not page_records:
                raise ValueError(f"No ЖК cards found on {next_url}; refusing partial output")
            complexes.update({record["complex_id"]: record for record in page_records})
            links = page.locator('nav[data-name="Pagination"] a[href]').evaluate_all(
                "nodes => nodes.map(node => node.href)"
            )
            next_page = next((url for url in links if parse_qs(urlparse(url).query).get("p") == [str(index + 2)]), None)
            if not next_page:
                if expected_count is not None and len(complexes) != expected_count:
                    raise ValueError(f"Expected {expected_count} ЖК, found {len(complexes)}; refusing partial output")
                logger.info("Reached final ЖК search page; collected %s unique complexes", len(complexes))
                return list(complexes.values())
            next_url = next_page
            if index + 1 < max_pages:
                time.sleep(delay_seconds)
        raise ValueError(f"Reached max_pages={max_pages}; refusing partial ЖК output")
    finally:
        page.close()


def save_complexes_raw(complexes: list[dict], path: Path = COMPLEXES_FILE) -> Path:
    """Store a complete crawl without replacing the previous file on failure."""
    if not complexes:
        raise ValueError("No ЖК to save")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(complexes, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    logger.info("Saved %s ЖК to %s", len(complexes), path)
    return path


def extract_complex_details(html: str) -> dict:
    """Read coordinates and minimum price embedded in a ЖК detail page."""
    location = re.search(
        r"get-map-preview/\?latitude=([\d.]+)&(?:amp;)?longitude=([\d.]+)(?:&(?:amp;)?[^\"<> ]+)*?newbuildingId=\d+",
        html,
    )
    price = re.search(r'"minPrice":"([\d.]+)"', html)
    details = {"latitude": None, "longitude": None, "price_from": None}
    if location:
        latitude, longitude = map(float, location.groups())
        if 55 <= latitude <= 57 and 91 <= longitude <= 95:
            details.update(latitude=latitude, longitude=longitude)
    if price:
        details["price_from"] = float(price.group(1))
    return details


def enrich_complexes(
    browser: Browser, complexes: list[dict], *, path: Path = COMPLEXES_FILE,
    delay_seconds: float = 2,
) -> tuple[int, int]:
    """Visit listed ЖК pages sequentially; keep partial progress and stop on HTTP errors."""
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be nonnegative")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    enriched = 0
    failure = None
    try:
        for record in complexes:
            if record.get("latitude") is not None and record.get("longitude") is not None:
                continue
            response = page.goto(record["url"], wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            if response is None or response.status != 200:
                failure = f"Stopped ЖК detail collection at {record['url']}: HTTP {response.status if response else 'no response'}"
                logger.warning(failure)
                break
            if SEARCH.city.lower() not in page.title().lower():
                failure = f"Unexpected ЖК city at {record['url']}"
                logger.warning(failure)
                break
            details = extract_complex_details(page.content())
            if details["latitude"] is not None:
                record.update(details)
                enriched += 1
                if enriched % 10 == 0:
                    save_complexes_raw(complexes, path)
            else:
                logger.warning("No verified coordinates at %s", record["url"])
            time.sleep(delay_seconds)
        save_complexes_raw(complexes, path)
        if failure:
            raise RuntimeError(failure)
        return enriched, sum(record.get("latitude") is not None for record in complexes)
    finally:
        page.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture public Cian pages for Krasnoyarsk")
    parser.add_argument("--complexes", action="store_true", help="Collect the full residential complex search and details")
    parser.add_argument("--resume-complexes", action="store_true", help="Enrich complexes already saved in RAW JSON")
    args = parser.parse_args(argv)
    if args.complexes and args.resume_complexes:
        parser.error("Choose only one complex collection mode")
    try:
        with sync_playwright() as playwright:
            browser = create_browser(playwright)
            try:
                if args.complexes or args.resume_complexes:
                    if args.complexes:
                        complexes = collect_all_complexes(browser)
                        save_complexes_raw(complexes)
                    else:
                        complexes = json.loads(COMPLEXES_FILE.read_text(encoding="utf-8"))
                        if not isinstance(complexes, list) or not complexes:
                            raise ValueError("No saved complexes to resume")
                    enriched, located = enrich_complexes(browser, complexes)
                    logger.info("Enriched %s complexes; %s/%s have coordinates", enriched, located, len(complexes))
                    return 0
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
    except (OSError, ValueError, RuntimeError, PlaywrightError):
        logger.exception("Could not capture Cian search page")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
