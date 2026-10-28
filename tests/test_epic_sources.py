import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from scripts.epic_sources import (
    FEEDS, KeylolPost, discover_candidates, epic_url, free_promotion, page_giveaway,
    product_slug, product_urls, read_queue, utc_date, verify_candidates, write_queue,
)


NOW = datetime(2026, 10, 28, 8, tzinfo=timezone.utc)
URL = "https://store.epicgames.com/p/mafia-hotel-eaea4c"


def offer(start, end, percentage=0):
    return {"startDate": start, "endDate": end, "discountSetting": {
        "discountType": "PERCENTAGE", "discountPercentage": percentage,
    }}


def page(price=0, end="2026-11-01T17:02:00.001Z", url=URL, label="Base Game", name="MAFIA HOTEL", platform="Windows"):
    data = {"@type": "Product", "url": url, "name": name, "description": "A game",
            "image": "https://cdn1.epicgames.com/image.png", "gamePlatform": [platform], "offers": {
                "@type": "AggregateOffer", "offers": [{
                    "url": url, "price": price, "priceValidUntil": end,
                    "availability": "https://schema.org/InStock",
                }]}}
    return '<script type="application/ld+json">' + json.dumps(data) + '</script><span>' + label + '</span>'


def response(text, url=URL):
    result = Mock(text=text, url=url)
    result.raise_for_status.return_value = None
    return result


class EpicSourcesTest(unittest.TestCase):
    def test_current_sale_does_not_hide_second_future_free_offer(self):
        item = {"promotions": {
            "promotionalOffers": [{"promotionalOffers": [offer("2026-10-19T15:00:00Z", "2026-11-02T16:00:00Z", 70)]}],
            "upcomingPromotionalOffers": [{"promotionalOffers": [
                offer("2026-12-10T16:00:00Z", "2027-01-07T16:00:00Z", 70),
                offer("2026-10-29T15:00:00Z", "2026-11-05T16:00:00Z"),
            ]}],
        }}
        result = free_promotion(item, NOW)
        self.assertTrue(result["is_upcoming"])
        self.assertEqual(utc_date(result["start_date"]), utc_date("2026-10-29T15:00:00Z"))

    def test_expired_offer_excluded_and_current_free_preferred(self):
        def group(items):
            return [{"promotionalOffers": items}]
        expired = offer("2026-10-01T15:00:00Z", "2026-10-27T20:00:00.001Z")
        self.assertIsNone(free_promotion({"promotions": {"promotionalOffers": group([expired])}}, NOW))
        result = free_promotion({"promotions": {"promotionalOffers": group([
            expired, offer("2026-10-24T15:00:00Z", "2026-11-01T17:02:00.001Z"),
        ])}}, NOW)
        self.assertFalse(result["is_upcoming"])

    def test_url_allowlist_and_locale_normalization(self):
        self.assertEqual(epic_url(URL.replace("/p/", "/zh-CN/p/") + "?utm_source=test"), URL)
        self.assertEqual(product_urls('<a href="' + URL + '?x=1&amp;y=2">Get</a>'), {URL})
        for url in [URL.replace("store.epicgames.com", "store.epicgames.com.evil.test"),
                    "https://evil.test/?next=" + URL, URL.replace("/p/", "/purchase/")]:
            self.assertIsNone(epic_url(url))

    def test_missing_catalog_mapping_uses_offer_mapping(self):
        self.assertEqual(product_slug({"catalogNs": {"mappings": []}, "offerMappings": [
            {"pageType": "productHome", "pageSlug": "sorry-were-closed-724c86"},
        ]}), "sorry-were-closed-724c86")

    def test_only_expiring_free_base_product_is_published(self):
        game, state = page_giveaway(page(), URL, NOW)
        self.assertEqual(state, "free")
        self.assertEqual(game["epic_slug"], "mafia-hotel-eaea4c")
        self.assertEqual(utc_date(game["end_date"]), utc_date("2026-11-01T17:02:00.001Z"))
        cases = [(page(price=6.99), "paid"),
                 (page(end="2026-10-27T20:00:00.001Z"), "expired"),
                 (page(end=None), "unknown"), (page(label="Add-On"), "unknown"),
                 (page(url=URL + "-dlc"), "unknown"), (page(name="Demo"), "unknown"),
                 (page(platform="Android"), "unknown"),
                 ('<script>"Base Game"</script>' + page(label="Add-On"), "unknown")]
        for text, expected in cases:
            with self.subTest(expected=expected, text=text[:50]):
                self.assertEqual(page_giveaway(text, URL, NOW), (None, expected))

    def test_timezones_and_fractional_seconds(self):
        self.assertEqual(utc_date("2026-10-28T04:00:00+08:00"), utc_date("2026-10-27T20:00:00Z"))
        self.assertLess(utc_date("2026-10-27T20:00:00.123Z"), NOW)
        self.assertIsNone(utc_date("限免进行中"))

    def test_keylol_nested_tables_do_not_truncate_first_post(self):
        body = KeylolPost()
        body.feed('<td id="postmessage_123"><table><tr><td>ad</td></tr></table>'
                  '<a href="' + URL + '">Get</a></td>'
                  '<td id="postmessage_124"><a href="https://store.epicgames.com/p/unrelated">Reply</a></td>')
        self.assertEqual(body.urls, {URL})

    def test_feeds_persist_candidates_and_follow_keylol_body(self):
        atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Epic game</title>'
                '<link href="https://www.reddit.com/r/example/post"/><content type="html">'
                '&lt;a href="' + URL + '"&gt;Get&lt;/a&gt;</content></entry></feed>')
        rss = ('<rss><channel><item><title>Epic Games Terraspace</title>'
               '<link>https://keylol.com/t1053326-1-1</link><description>truncated...</description>'
               '</item></channel></rss>')
        terra = "https://store.epicgames.com/p/dimond-hunt-03a766"
        def get(url, **kwargs):
            if url == FEEDS[0][1]:
                return response(atom)
            if url == FEEDS[1][1]:
                raise RuntimeError("temporary failure")
            if url == FEEDS[2][1]:
                return response(rss)
            self.assertEqual(url, "https://keylol.com/t1053326-1-1")
            return response('<td class="t_f" id="postmessage_123"><a href="' + terra + '">Get</a></td>')
        old = "https://store.epicgames.com/p/old-free-game"
        queue = discover_candidates(get, {}, {old: {"last_seen": NOW.isoformat()}}, NOW)
        self.assertEqual(set(queue), {URL, terra, old})
        self.assertEqual(queue[terra]["sources"], ["Keylol RSS"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            write_queue(queue, path)
            self.assertEqual(read_queue(path), queue)

    def test_verification_limit_resumes_and_tracks_paid_products(self):
        terra = "https://store.epicgames.com/p/dimond-hunt-03a766"
        queue = {URL: {}, terra: {"last_checked": "2026-10-27T00:00:00Z"}}
        get = Mock(return_value=response(page(), URL.replace("/p/", "/en-US/p/")))
        games, inactive = verify_candidates(get, {}, queue, now=NOW, limit=1)
        self.assertEqual(len(games), 1)
        self.assertEqual(inactive, set())
        get.return_value = response(page(price=6.99, url=terra), terra)
        games, inactive = verify_candidates(get, {}, queue, now=NOW, limit=1)
        self.assertEqual(games, [])
        self.assertEqual(inactive, {"dimond-hunt-03a766"})
        self.assertEqual(queue[terra]["last_result"], "paid")

    def test_verification_failure_does_not_mark_product_paid(self):
        queue = {URL: {}}
        get = Mock(side_effect=RuntimeError("HTTP 403"))
        self.assertEqual(verify_candidates(get, {}, queue, now=NOW), ([], set()))
        self.assertEqual(queue[URL]["last_result"], "unavailable")


if __name__ == "__main__":
    unittest.main()
