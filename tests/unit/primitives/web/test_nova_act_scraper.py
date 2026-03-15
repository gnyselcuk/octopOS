"""Unit tests for primitives/web/nova_act_scraper.py."""

from unittest.mock import patch

from src.primitives.web.nova_act_scraper import NovaActScraper


class TestNovaActScraper:
    """Test NovaActScraper helper behavior."""

    def test_prepare_nova_act_source_truncates_large_html_snapshot(self):
        scraper = NovaActScraper()
        html = "<html><body>" + (" price " * 5000) + "</body></html>"

        with patch("src.primitives.web.nova_act_scraper.HAS_BS4", False):
            source, label, truncated = scraper._prepare_nova_act_source(html, "bitcoin price")

        assert label == "RENDERED PAGE TEXT"
        assert truncated is True
        assert len(source) == scraper.MAX_NOVA_ACT_SOURCE_CHARS

    def test_prepare_nova_act_source_compacts_whitespace(self):
        scraper = NovaActScraper()

        with patch("src.primitives.web.nova_act_scraper.HAS_BS4", False):
            source, _, _ = scraper._prepare_nova_act_source(
                "<html>  BTC\n\n   123   USD   </html>",
                "btc price"
            )

        assert "BTC" in source
        assert "USD" in source

    def test_extract_signal_lines_prefers_price_like_lines(self):
        scraper = NovaActScraper()

        signal = scraper._extract_signal_lines(
            "Header\nBitcoin BTC\n$82,000 USD\nFooter",
            "get bitcoin current price",
        )

        assert "Bitcoin BTC" in signal
        assert "$82,000 USD" in signal
