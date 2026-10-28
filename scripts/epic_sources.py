"""Discover Epic giveaways in community feeds and verify them with Epic data.

Community titles and dates never authorize publication. Only an Epic promotion
or a matching official product with a zero-price, expiring offer does.
"""

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


FEEDS = (
    ("FreeGameFindings RSS", "https://www.reddit.com/r/FreeGameFindings/new/.rss?limit=100"),
    ("EpicGamesPC RSS", "https://www.reddit.com/r/EpicGamesPC/new/.rss?limit=100"),
    ("Keylol RSS", "https://keylol.com/forum.php?mod=rss&fid=319"),
)
ATOM = "{http://www.w3.org/2005/Atom}"
QUEUE_FILE = "epic_candidates.json"


def utc_date(value):
    if not value:
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def epic_url(value):
    parsed = urlparse(html.unescape(str(value)).strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "store.epicgames.com":
        return None
    match = re.fullmatch(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?p/([a-z0-9-]+)(?:/home)?/?", parsed.path, re.I)
    return "https://store.epicgames.com/p/" + match[1].lower() if match else None


def product_urls(text):
    text = html.unescape(text or "").replace("\\/", "/")
    urls = re.findall(r"https://store\.epicgames\.com/[^\s<>\"'\[\]{}]+", text, re.I)
    return {url for raw in urls if (url := epic_url(raw.rstrip(".,;)")))}


def feed_entries(text):
    root = ET.fromstring(text)
    for entry in root.findall(".//item"):
        yield entry.findtext("title", ""), entry.findtext("description", ""), entry.findtext("link", "")
    for entry in root.findall(ATOM + "entry"):
        link = entry.find(ATOM + "link")
        yield entry.findtext(ATOM + "title", ""), entry.findtext(ATOM + "content", ""), link.get("href", "") if link is not None else ""


class KeylolPost(HTMLParser):
    """Collect links in the first post, including inside nested layout tables."""

    def __init__(self):
        super().__init__()
        self.urls = set()
        self._depth = 0
        self._finished = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td":
            if self._depth:
                self._depth += 1
            elif not self._finished and re.fullmatch(r"postmessage_\d+", attrs.get("id", "")):
                self._depth = 1
        if self._depth and tag == "a":
            url = epic_url(attrs.get("href", ""))
            if url:
                self.urls.add(url)

    def handle_endtag(self, tag):
        if tag == "td" and self._depth:
            self._depth -= 1
            if not self._depth:
                self._finished = True


def read_queue(path=QUEUE_FILE):
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {url: item for raw, item in data.items() if isinstance(item, dict) and (url := epic_url(raw))}
    except (OSError, ValueError, AttributeError) as exc:
        print(f"⚠️ Epic 候选队列读取失败：{exc}")
        return {}


def write_queue(queue, path=QUEUE_FILE):
    Path(path).write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_candidates(get, headers, queue=None, now=None):
    now = utc_date(now) or datetime.now(timezone.utc)
    queue = dict(queue or {})
    # Retain candidates after they leave a short feed, without growing forever.
    queue = {url: item for url, item in queue.items()
             if (utc_date(item.get("last_seen")) or now) >= now - timedelta(days=45)}
    for source, feed_url in FEEDS:
        added = 0
        try:
            response = get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            for title, content, post_url in feed_entries(response.text):
                if re.search(r"\b(?:mobile|android|ios)\b", title, re.I) and not re.search(r"\bPC\b", title, re.I):
                    continue
                # In these feeds only the giveaway post itself is authoritative
                # discovery context; Steam references in replies are unrelated.
                urls = product_urls(content)
                if source == "Keylol RSS" and ("epic" in title.lower()):
                    parsed = urlparse(post_url)
                    if parsed.scheme == "https" and parsed.netloc == "keylol.com" and re.fullmatch(r"/t\d+-1-1", parsed.path):
                        try:
                            post = get(post_url, headers=headers, timeout=15)
                            post.raise_for_status()
                            # Exclude navigation, signatures and unrelated replies.
                            body = KeylolPost()
                            body.feed(post.text)
                            urls.update(body.urls)
                        except Exception as exc:
                            print(f"⚠️ Keylol Epic 正文读取失败 {post_url}: {exc}")
                for url in sorted(urls):
                    added += url not in queue
                    item = queue.setdefault(url, {"first_seen": now.isoformat()})
                    item["last_seen"] = now.isoformat()
                    item["sources"] = sorted(set(item.get("sources", [])) | {source})
                    item["posts"] = sorted(set(item.get("posts", [])) | {post_url})[-5:]
            print(f"🧩 Epic {source}: 新增 {added} 个候选")
        except Exception as exc:
            print(f"⚠️ Epic {source} 抓取失败，保留已有候选：{exc}")
    return queue


def free_promotion(item, now=None):
    """Inspect every offer, including future freebies during a current sale."""
    now = utc_date(now) or datetime.now(timezone.utc)
    matches = []
    for key in ("promotionalOffers", "upcomingPromotionalOffers"):
        for group in (item.get("promotions") or {}).get(key, []) or []:
            for offer in group.get("promotionalOffers", []) or []:
                discount = offer.get("discountSetting", {})
                start, end = utc_date(offer.get("startDate")), utc_date(offer.get("endDate"))
                if discount.get("discountType") != "PERCENTAGE" or discount.get("discountPercentage") != 0:
                    continue
                if start and end and start < end and end > now:
                    matches.append((start > now, start, end))
    if not matches:
        return None
    upcoming, start, end = min(matches)
    return {"is_upcoming": upcoming, "start_date": start.isoformat(), "end_date": end.isoformat()}


def product_slug(item):
    for mapping in (item.get("catalogNs") or {}).get("mappings", []) or []:
        if mapping.get("pageType") == "productHome" and mapping.get("pageSlug"):
            return mapping["pageSlug"].lower()
    for mapping in item.get("offerMappings", []) or []:
        if mapping.get("pageType") == "productHome" and mapping.get("pageSlug"):
            return mapping["pageSlug"].lower()
    url = epic_url("https://store.epicgames.com/p/" + str(item.get("productSlug") or ""))
    return url.rsplit("/", 1)[-1] if url else None


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.json_scripts = []
        self.text = []
        self._script = None
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._hidden += 1
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._script = []

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.json_scripts.append("".join(self._script))
            self._script = None
        if tag in ("script", "style"):
            self._hidden = max(0, self._hidden - 1)

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        elif not self._hidden:
            self.text.append(data)


def page_giveaway(text, url, now=None):
    """Return (game, state); paid/expired are definitive, unknown is retryable."""
    now = utc_date(now) or datetime.now(timezone.utc)
    url = epic_url(url)
    if not url:
        return None, "unknown"
    page = ProductPage()
    page.feed(text)
    for script in page.json_scripts:
        try:
            data = json.loads(script)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for product in nodes:
            if not isinstance(product, dict) or product.get("@type") != "Product":
                continue
            if epic_url(product.get("url") or product.get("@id")) != url:
                continue
            platforms = product.get("gamePlatform") or product.get("operatingSystem") or []
            platforms = [platforms] if isinstance(platforms, str) else platforms
            if not any("windows" in str(platform).lower() for platform in platforms):
                continue
            aggregate = product.get("offers") or {}
            offers = aggregate if isinstance(aggregate, list) else aggregate.get("offers", [aggregate])
            for offer in offers:
                if not isinstance(offer, dict) or epic_url(offer.get("url")) != url:
                    continue
                try:
                    price = Decimal(str(offer["price"]))
                except (KeyError, InvalidOperation):
                    continue
                if not price.is_finite() or price < 0:
                    continue
                if price > 0:
                    return None, "paid"
                end = utc_date(offer.get("priceValidUntil"))
                if end and end <= now:
                    return None, "expired"
                # An expiring free BASE GAME excludes ordinary F2P, DLC and demos.
                if not end or not re.search(r"\bBase Game\b", " ".join(page.text)):
                    continue
                if offer.get("availability") != "https://schema.org/InStock":
                    continue
                if re.search(r"\b(?:free (?:trial|weekend)|play for free|demo)\b", str(product.get("name", "")), re.I):
                    continue
                image = product.get("image", "")
                if isinstance(image, list):
                    image = image[0] if image else ""
                if isinstance(image, dict):
                    image = image.get("url", "")
                return {
                    "zh_title": product.get("name") or url.rsplit("/", 1)[-1],
                    "thumbnail": image,
                    "short_description": product.get("description", ""),
                    "end_date": end.isoformat(), "platform": "Epic Games",
                    "epic_slug": url.rsplit("/", 1)[-1], "type": "100_off",
                    "is_upcoming": False, "title_url": url, "button_url": url,
                }, "free"
    return None, "unknown"


def verify_candidates(get, headers, queue, skip_slugs=(), now=None, limit=30):
    now = utc_date(now) or datetime.now(timezone.utc)
    games, inactive = [], set()
    entries = sorted(queue.items(), key=lambda pair: pair[1].get("last_checked", ""))
    checked = 0
    for url, candidate in entries:
        slug = url.rsplit("/", 1)[-1]
        if slug in skip_slugs:
            continue
        if checked >= limit:
            break
        checked += 1
        candidate["last_checked"] = now.isoformat()
        try:
            # English labels make the base-game check independent of locale.
            response = get(url.replace("/p/", "/en-US/p/", 1), headers=headers, timeout=15)
            response.raise_for_status()
            if epic_url(response.url) != url:
                raise ValueError("Epic response redirected away from the requested product")
            game, state = page_giveaway(response.text, url, now)
            candidate["last_result"] = state
            if game:
                games.append(game)
            elif state in ("paid", "expired"):
                inactive.add(slug)
        except Exception as exc:
            candidate["last_result"] = "unavailable"
            print(f"⚠️ Epic 官方核验失败，暂不自动发布 {slug}: {exc}")
    print(f"🔎 Epic 社区候选 {len(queue)} 个，本轮核验 {checked} 个，通过 {len(games)} 个，已收费/过期 {len(inactive)} 个")
    return games, inactive
