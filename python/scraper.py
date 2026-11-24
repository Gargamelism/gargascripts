#!/usr/bin/env python3
"""
Torrent site scraper: login, search, paginate, stop by date.
Usage: python scraper.py [--config config.json]
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import dacite
import dateparser
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


class _TqdmHandler(logging.StreamHandler):
    def emit(self, record):
        tqdm.write(self.format(record))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[_TqdmHandler()],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Credentials:
    username: str
    password: str


@dataclass
class SearchConfig:
    query: str
    order: str = "desc"
    orderby: str = "added"
    inclusions: str = ""
    exclusions: str = ""
    inclusions_op: str = "ALL"
    min_seeders: int = 1
    size_min: str = ""
    size_max: str = ""


@dataclass
class PaginationConfig:
    start_page: int = 1
    max_pages: int = 100
    delay_seconds: int = 10


@dataclass
class StopCondition:
    max_age: str = "7 days"


@dataclass
class OutputConfig:
    file: str = "results.json"


@dataclass
class Config:
    base_url: str
    credentials: Credentials
    searches: list
    pagination: PaginationConfig
    stop_condition: StopCondition
    output: OutputConfig
    exclusions: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TorrentItem:
    search_query: str
    title: str
    size: str
    date_str: str
    seeders: str
    leechers: str
    link: str


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str) -> Config:
    with open(path) as f:
        raw = json.load(f)

    searches = [dacite.from_dict(SearchConfig, s) for s in raw.get("searches", [])]
    raw["searches"] = searches

    return dacite.from_dict(Config, raw, config=dacite.Config(strict=False))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(session: requests.Session, base_url: str, creds: Credentials) -> None:
    url = f"{base_url}/user/account/login/"
    payload = {
        "username": creds.username,
        "password": creds.password,
        "is_forum_login": "",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{base_url}/",
        "Origin": base_url,
    }
    resp = session.post(url, data=payload, headers=headers, allow_redirects=True)
    resp.raise_for_status()

    if "PHPSESSID" not in session.cookies:
        raise RuntimeError("Login failed: PHPSESSID cookie not set — check credentials.")

    log.info("Login successful (PHPSESSID acquired)")


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def fetch_page(
    session: requests.Session,
    base_url: str,
    search: SearchConfig,
    page: int,
    delay_seconds: int,
) -> str:
    params = {
        "query": search.query,
        "page": page,
        "inclusions": search.inclusions,
        "exclusions": search.exclusions,
        "inclusionsOp": search.inclusions_op,
        "order": search.order,
        "orderby": search.orderby,
    }
    headers = {}
    if page > 1:
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    url = f"{base_url}/torrents/browse"
    log.info("Fetching page %d", page)
    resp = session.get(url, params=params, headers=headers)
    resp.raise_for_status()

    time.sleep(delay_seconds)
    return resp.text


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------

def extract_table_html(raw: str) -> Optional[str]:
    soup = BeautifulSoup(raw, "html.parser")
    table = soup.find(id="torrenttable")
    return str(table) if table else None


# ---------------------------------------------------------------------------
# Torrent row parsing
# ---------------------------------------------------------------------------

def _find_cell(texts: list, predicate, skip_first: bool = False, skip_value: Optional[str] = None) -> Optional[str]:
    for i, t in enumerate(texts):
        if skip_first and i == 0:
            continue
        if t == skip_value:
            continue
        if predicate(t):
            return t
    return None


def _looks_like_size(text: str) -> bool:
    return bool(re.search(r"\d+(\.\d+)?\s*(B|KB|MB|GB|TB)", text, re.IGNORECASE))


def _looks_like_date(text: str) -> bool:
    return bool(re.search(
        r"(\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago"
        r"|\d{4}-\d{2}-\d{2}"
        r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b)",
        text, re.IGNORECASE,
    ))



_DATE_IN_CELL_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?")


def _extract_date_from_cell(text: str) -> str:
    """Extract a bare YYYY-MM-DD[ HH:MM:SS] from a cell that may contain other text."""
    m = _DATE_IN_CELL_RE.search(text)
    return m.group(0) if m else text


def parse_torrents(table_html: str, query: str, base_url: str) -> list:
    soup = BeautifulSoup(table_html, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return []

    results = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        title_span = row.find("span", class_="title")
        title_anchor = title_span.find("a", href=True) if title_span else None
        title = title_anchor.get_text(strip=True) if title_anchor else ""
        href = title_anchor["href"] if title_anchor else ""
        link = base_url + href if href.startswith("/") else href

        cell_texts = [c.get_text(strip=True) for c in cells]
        size = _find_cell(cell_texts, _looks_like_size)
        raw_date = _find_cell(cell_texts, _looks_like_date)
        date_str = _extract_date_from_cell(raw_date) if raw_date else ""

        seeders_td = row.find("td", class_="seeders")
        leechers_td = row.find("td", class_="leechers")
        seeders = seeders_td.get_text(strip=True) if seeders_td else ""
        leechers = leechers_td.get_text(strip=True) if leechers_td else ""

        results.append(TorrentItem(
            search_query=query,
            title=title,
            size=size or "",
            date_str=date_str,
            seeders=seeders or "",
            leechers=leechers or "",
            link=link,
        ))

    return results


# ---------------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------------

_DATEPARSER_SETTINGS = {
    "RETURN_TIME_AS_PERIOD": False,
    "PREFER_DAY_OF_MONTH": "first",
    "TIMEZONE": "UTC",
    "RETURN_AS_TIMEZONE_AWARE": True,
}


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    dt = dateparser.parse(date_str, settings=_DATEPARSER_SETTINGS)
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def cutoff_datetime(max_age_str: str) -> datetime:
    """Return the UTC datetime before which torrents are considered too old."""
    # Parse "7 days" → timedelta by asking dateparser to interpret "<n> <unit> ago"
    ref = dateparser.parse(
        f"{max_age_str} ago",
        settings={**_DATEPARSER_SETTINGS},
    )
    if ref is None:
        raise ValueError(f"Cannot parse max_age: {max_age_str!r}")
    return ref


def is_too_old(date_str: str, cutoff: datetime) -> bool:
    dt = parse_date(date_str)
    if dt is None:
        log.warning("Could not parse date %r — skipping age check for this item", date_str)
        return False
    return dt < cutoff


_SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def parse_size_bytes(size_str: str) -> Optional[int]:
    match = re.search(r"([\d.]+)\s*(B|KB|MB|GB)", size_str, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    return int(value * _SIZE_UNITS[unit])


def _passes_seeders(item: TorrentItem, search: SearchConfig) -> bool:
    try:
        return int(item.seeders or 0) >= search.min_seeders
    except ValueError:
        return False


def _passes_title_words(item: TorrentItem, search: SearchConfig) -> bool:
    return all(word in item.title.lower() for word in search.query.lower().split())


def _passes_exclusion(item: TorrentItem, exclusion_terms: list) -> bool:
    for term in exclusion_terms:
        if re.search(r'\b' + re.escape(term) + r'\b', item.title, re.IGNORECASE):
            return False
    return True


def _passes_size(
    item: TorrentItem,
    size_min_bytes: Optional[int] = None,
    size_max_bytes: Optional[int] = None,
    search: Optional[SearchConfig] = None,
) -> bool:
    if search and (search.size_min or search.size_max):
        size_min_bytes = parse_size_bytes(search.size_min) if search.size_min else None
        size_max_bytes = parse_size_bytes(search.size_max) if search.size_max else None

    if size_min_bytes is None and size_max_bytes is None:
        return True
    item_bytes = parse_size_bytes(item.size)
    if item_bytes is None:
        return False
    if size_min_bytes is not None and item_bytes < size_min_bytes:
        return False
    if size_max_bytes is not None and item_bytes > size_max_bytes:
        return False
    return True


# ---------------------------------------------------------------------------
# Pagination detection
# ---------------------------------------------------------------------------

def has_next_page(table_html: str, current_page: int) -> bool:
    soup = BeautifulSoup(table_html, "html.parser")

    tbody = soup.find("tbody")
    if not tbody or not tbody.find("tr"):
        return False

    next_btn = soup.find("a", class_="next-btn")
    if next_btn:
        target = next_btn.get("data-target", "")
        try:
            return int(target) > current_page
        except (ValueError, TypeError):
            return True  # present but unparseable — assume next exists

    # No next-btn found; if there's no pagination at all it's a single-page result
    pagination = soup.find("ul", class_="pagination")
    return pagination is None


# ---------------------------------------------------------------------------
# Per-search loop
# ---------------------------------------------------------------------------

def run_search(
    session: requests.Session,
    base_url: str,
    search: SearchConfig,
    pagination: PaginationConfig,
    cutoff: datetime,
    progress: tqdm,
    exclusion_terms: list[str],
) -> list:
    all_items = []
    end_page = pagination.start_page + pagination.max_pages
    for page in range(pagination.start_page, end_page):
        raw = fetch_page(session, base_url, search, page, pagination.delay_seconds)
        table_html = extract_table_html(raw)

        if not table_html:
            log.info("No table content on page %d — stopping search", page)
            break

        items = parse_torrents(table_html, search.query, base_url)
        if not items:
            log.info("No torrent rows on page %d — stopping search", page)
            break

        size_min_bytes = parse_size_bytes(search.size_min) if search.size_min else None
        size_max_bytes = parse_size_bytes(search.size_max) if search.size_max else None
        filters = [
            lambda item: _passes_seeders(item, search),
            lambda item: _passes_title_words(item, search),
            lambda item: _passes_size(item, size_min_bytes, size_max_bytes),
            lambda item: _passes_exclusion(item, exclusion_terms),
        ]

        stop = False
        page_kept = 0
        for count, item in enumerate(items, 1):
            if item.date_str and is_too_old(item.date_str, cutoff):
                log.info(
                    "Cutoff reached on page %d after %d torrents — stopping search",
                    page, count,
                )
                stop = True
                break
            if all(predicate(item) for predicate in filters):
                all_items.append(item)
                page_kept += 1

        progress.set_postfix(page=page, kept=len(all_items))
        progress.update(1)
        log.info("Page %d: +%d items (total: %d)", page, page_kept, len(all_items))

        if stop:
            break
        if not has_next_page(table_html, page):
            log.info("No next page after page %d — stopping search", page)
            break

    log.info("Search done: %d items", len(all_items))
    return all_items


# ---------------------------------------------------------------------------
# Browse-and-filter loop
# ---------------------------------------------------------------------------

def run_browse(
    session: requests.Session,
    base_url: str,
    searches: list,
    pagination: PaginationConfig,
    cutoff: datetime,
    progress: tqdm,
    exclusion_terms: list = (),
) -> list:
    browse_search = SearchConfig(query="")

    filters = [
        lambda item, search: _passes_seeders(item, search),
        lambda item, search: _passes_title_words(item, search),
        lambda item, search: _passes_size(item, search=search),
    ]
    
    all_items = []
    end_page = pagination.start_page + pagination.max_pages
    for page in range(pagination.start_page, end_page):
        raw = fetch_page(session, base_url, browse_search, page, pagination.delay_seconds)
        table_html = extract_table_html(raw)

        if not table_html:
            log.info("No table content on page %d — stopping browse", page)
            break

        items = parse_torrents(table_html, "", base_url)
        if not items:
            log.info("No torrent rows on page %d — stopping browse", page)
            break

        stop = False
        page_kept = 0
        for count, item in enumerate(items, 1):
            if item.date_str and is_too_old(item.date_str, cutoff):
                log.info(
                    "Cutoff reached on page %d after %d torrents — stopping browse",
                    page, count,
                )
                stop = True
                break

            if not _passes_exclusion(item, exclusion_terms):
                continue
            for search_item in searches:
                if all(predicate(item, search_item) for predicate in filters):
                    all_items.append(TorrentItem(
                        search_query=search_item.query,
                        title=item.title,
                        size=item.size,
                        date_str=item.date_str,
                        seeders=item.seeders,
                        leechers=item.leechers,
                        link=item.link,
                    ))
                    page_kept += 1

        progress.set_postfix(page=page, kept=len(all_items))
        progress.update(1)
        log.info("Page %d: +%d items (total: %d)", page, page_kept, len(all_items))

        if stop:
            break
        if not has_next_page(table_html, page):
            log.info("No next page after page %d — stopping browse", page)
            break

    log.info("Browse done: %d items", len(all_items))
    return all_items


# ---------------------------------------------------------------------------
# deduplication
# ---------------------------------------------------------------------------
def deduplicate_results(all_results) -> list:
    seen_links = set()
    unique_results = []
    for item in all_results:
        if item.link not in seen_links:
            unique_results.append(item)
            seen_links.add(item.link)
    log.info("Deduplicated results: %d unique items", len(unique_results))
    return unique_results

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def load_existing_results(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    items = [dacite.from_dict(TorrentItem, d) for d in data]
    log.info("Loaded %d existing items from %s", len(items), path)
    return items


def write_output(items: list, path: str) -> None:
    data = [asdict(item) for item in items]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("Wrote %d items to %s", len(data), path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Torrent site scraper")
    parser.add_argument("--config", default="config.json", help="Path to JSON config file")
    
    # config overrides
    parser.add_argument("--max-age", help="Override max_age stop condition (e.g. '3 days')")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge with existing output file, deduplicating by link (new results win).",
    )
    parser.add_argument(
        "--browse",
        action="store_true",
        help="Walk the global /torrents/browse feed once and filter against all configured queries locally.",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        log.error("Config file not found: %s", args.config)
        sys.exit(1)
    except Exception as e:
        log.error("Failed to load config: %s", e)
        sys.exit(1)

    # config overrides
    if args.max_age:
        config.stop_condition.max_age = args.max_age


    cutoff = cutoff_datetime(config.stop_condition.max_age)
    log.info(
        "Stopping torrents older than %r (cutoff: %s)",
        config.stop_condition.max_age,
        cutoff.strftime("%Y-%m-%d %H:%M UTC"),
    )

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    })

    try:
        login(session, config.base_url, config.credentials)
    except Exception as e:
        log.error("Login failed: %s", e)
        sys.exit(1)

    all_results = []
    if args.browse:
        with tqdm(desc="Pages", unit="page") as page_bar:
            try:
                all_results = run_browse(
                    session, config.base_url, config.searches, config.pagination, cutoff, page_bar, config.exclusions,
                )
            except Exception as e:
                log.error("Browse failed: %s", e)
    else:
        total = len(config.searches)
        with tqdm(total=total, desc="Searches", unit="search") as search_bar:
            for i, search in enumerate(config.searches, 1):
                search_bar.set_description(f"Search {i}/{total}")
                with tqdm(desc="Pages", unit="page", leave=False) as page_bar:
                    try:
                        items = run_search(session, config.base_url, search, config.pagination, cutoff, page_bar, config.exclusions)
                        all_results.extend(items)
                    except Exception as e:
                        log.error("Search %d/%d failed: %s", i, total, e)
                search_bar.update(1)

    if args.append:
        existing = load_existing_results(config.output.file)
        # New results first so they win during link-based deduplication.
        all_results = all_results + existing

    all_results = deduplicate_results(all_results)

    write_output(all_results, config.output.file)


if __name__ == "__main__":
    main()
