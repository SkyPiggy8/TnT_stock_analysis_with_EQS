import sys
import types
import unittest
from unittest import mock

import pandas as pd
import pytest

import tradingagents.default_config as default_config

try:
    import yfinance  # noqa: F401
except ImportError:
    fake_yfinance = types.ModuleType("yfinance")
    fake_yfinance_exceptions = types.ModuleType("yfinance.exceptions")

    class YFRateLimitError(Exception):
        pass

    fake_yfinance_exceptions.YFRateLimitError = YFRateLimitError
    fake_yfinance.exceptions = fake_yfinance_exceptions
    sys.modules.setdefault("yfinance", fake_yfinance)
    sys.modules.setdefault("yfinance.exceptions", fake_yfinance_exceptions)

try:
    import stockstats  # noqa: F401
except ImportError:
    fake_stockstats = types.ModuleType("stockstats")
    fake_stockstats.wrap = lambda data: data
    sys.modules.setdefault("stockstats", fake_stockstats)

from tradingagents.dataflows import interface
from tradingagents.dataflows import akshare_news_provider as provider
from tradingagents.dataflows.config import set_config


@pytest.mark.unit
class TestAkShareNewsProvider(unittest.TestCase):
    def setUp(self):
        provider._CACHE.clear()
        set_config(default_config.DEFAULT_CONFIG.copy())

    def tearDown(self):
        provider._CACHE.clear()
        set_config(default_config.DEFAULT_CONFIG.copy())

    def test_cls_news_normalizes_rows(self):
        fake_akshare = types.SimpleNamespace()
        fake_akshare.stock_info_global_cls = lambda symbol="全部": pd.DataFrame(
            {
                "标题": ["重大公告"],
                "内容": ["人工智能产业链活跃"],
                "发布时间": ["2026-06-10 09:30:00"],
                "链接": ["https://example.test/cls"],
            }
        )

        with mock.patch.object(provider, "ak", fake_akshare):
            rows = provider.get_akshare_cls_news(limit=1)

        self.assertEqual(rows[0]["source"], "财联社")
        self.assertEqual(rows[0]["title"], "重大公告")
        self.assertEqual(rows[0]["datetime"], "2026-06-10 09:30:00")
        self.assertEqual(rows[0]["url"], "https://example.test/cls")
        self.assertIn("标题", rows[0]["raw"])

    def test_ths_news_normalizes_rows(self):
        fake_akshare = types.SimpleNamespace()
        fake_akshare.stock_info_global_ths = lambda: pd.DataFrame(
            {
                "标题": ["市场快讯"],
                "内容": ["半导体板块走强"],
                "发布日期": ["2026-06-10 10:00:00"],
                "链接": ["https://example.test/ths"],
            }
        )

        with mock.patch.object(provider, "ak", fake_akshare):
            rows = provider.get_akshare_ths_news(limit=1)

        self.assertEqual(rows[0]["source"], "同花顺")
        self.assertEqual(rows[0]["title"], "市场快讯")
        self.assertEqual(rows[0]["datetime"], "2026-06-10 10:00:00")

    def test_cn_market_news_filters_then_falls_back(self):
        fake_news = [
            {
                "source": "财联社",
                "title": "浪潮信息发布服务器新品",
                "content": "000977 相关产业链关注度提升",
                "datetime": "2026-06-10 10:00:00",
                "url": "",
                "raw": {},
            },
            {
                "source": "同花顺",
                "title": "大盘震荡整理",
                "content": "市场成交额小幅放大",
                "datetime": "2026-06-10 09:00:00",
                "url": "https://example.test/market",
                "raw": {},
            },
        ]

        with mock.patch.object(provider, "_collect_news", return_value=fake_news):
            with mock.patch.object(provider, "_stock_terms", return_value=["000977", "浪潮信息"]):
                result = provider.get_cn_market_news("000977.SZ", "2026-06-10")
            with mock.patch.object(provider, "_stock_terms", return_value=["不存在的股票"]):
                fallback = provider.get_cn_market_news("000000.SZ", "2026-06-10")

        self.assertIn("浪潮信息发布服务器新品", result)
        self.assertNotIn("大盘震荡整理", result)
        self.assertIn("fallback", fallback)
        self.assertIn("大盘震荡整理", fallback)

    def test_normalize_cn_ticker(self):
        self.assertEqual(provider.normalize_cn_ticker("000966.SZ"), "000966")
        self.assertEqual(provider.normalize_cn_ticker("600519.SS"), "600519")
        self.assertEqual(provider.normalize_cn_ticker("600519.SH"), "600519")
        self.assertEqual(provider.normalize_cn_ticker("300750.SZ"), "300750")
        self.assertEqual(provider.normalize_cn_ticker("000966"), "000966")

    def test_get_cn_stock_name_uses_spot_cache(self):
        calls = {"count": 0}
        fake_akshare = types.SimpleNamespace()

        def stock_zh_a_spot_em():
            calls["count"] += 1
            return pd.DataFrame(
                {
                    "\u4ee3\u7801": ["000966", "600519"],
                    "\u540d\u79f0": ["\u957f\u6e90\u7535\u529b", "\u8d35\u5dde\u8305\u53f0"],
                }
            )

        fake_akshare.stock_zh_a_spot_em = stock_zh_a_spot_em

        with mock.patch.object(provider, "ak", fake_akshare):
            self.assertEqual(provider.get_cn_stock_name("000966.SZ"), "\u957f\u6e90\u7535\u529b")
            self.assertEqual(provider.get_cn_stock_name("600519.SS"), "\u8d35\u5dde\u8305\u53f0")

        self.assertEqual(calls["count"], 1)

    def test_build_keywords_strips_common_suffixes(self):
        keywords = provider.build_keywords(
            "000966.SZ",
            "\u6e56\u5317\u80fd\u6e90\u80a1\u4efd",
            extra_keywords=["\u7535\u529b", "\u706b\u7535", "\u7eff\u7535"],
        )

        self.assertIn("000966", keywords)
        self.assertIn("\u6e56\u5317\u80fd\u6e90\u80a1\u4efd", keywords)
        self.assertIn("\u6e56\u5317\u80fd\u6e90", keywords)
        self.assertIn("\u7535\u529b", keywords)

    def test_filter_news_by_keywords_returns_fallback_notice(self):
        news = [
            {"title": "\u5e02\u573a\u5feb\u8baf", "content": "\u5927\u76d8\u9707\u8361", "datetime": "2026-06-10 09:00:00"},
        ]
        filtered = provider.filter_news_by_keywords(news, ["000966", "\u957f\u6e90\u7535\u529b"])

        self.assertEqual(filtered[0]["title"], "\u5e02\u573a\u5feb\u8baf")
        self.assertIn("\u672a\u627e\u5230\u76f4\u63a5\u5339\u914d", filtered[0]["_fallback_notice"])

    def test_classify_cn_news_impact(self):
        item = {
            "title": "\u516c\u53f8\u6536\u5230\u76d1\u7ba1\u51fd\u5e76\u62ab\u9732\u51cf\u6301\u8ba1\u5212",
            "content": "\u4e1a\u7ee9\u4e0b\u964d\uff0c\u7535\u4ef7\u6ce2\u52a8\u5e26\u6765\u98ce\u9669\u3002",
        }

        impact = provider.classify_cn_news_impact(item, "000966.SZ", "\u957f\u6e90\u7535\u529b")

        self.assertEqual(impact["importance"], "high")
        self.assertEqual(impact["sentiment"], "negative")
        self.assertIn("\u76d1\u7ba1", impact["categories"])
        self.assertIn("\u516c\u544a", impact["categories"])
        self.assertIn("\u5927\u5b97\u5546\u54c1", impact["categories"])
        self.assertIn("\u51cf\u6301", impact["matched_keywords"])

    def test_format_news_block_includes_impact_label_content_and_url(self):
        news = [
            {
                "source": "\u8d22\u8054\u793e",
                "title": "\u653f\u7b56\u652f\u6301\u80fd\u6e90\u884c\u4e1a",
                "content": "\u53d1\u6539\u59d4\u63a8\u52a8\u7eff\u7535\u9879\u76ee\uff0c\u516c\u53f8\u8ba2\u5355\u589e\u957f\u3002",
                "datetime": "2026-06-10 09:00:00",
                "url": "https://example.test/news",
            }
        ]

        text = provider._format_news_block("test", news, 10)

        self.assertIn("[medium/positive/\u653f\u7b56,\u884c\u4e1a]", text)
        self.assertIn("\u8d22\u8054\u793e 2026-06-10 09:00:00 \u653f\u7b56\u652f\u6301\u80fd\u6e90\u884c\u4e1a", text)
        self.assertIn("\u53d1\u6539\u59d4\u63a8\u52a8\u7eff\u7535\u9879\u76ee", text)
        self.assertIn("https://example.test/news", text)

    def test_route_to_vendor_can_use_akshare_news(self):
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"akshare_news": lambda *args: "akshare-news-ok"}},
            clear=False,
        ):
            set_config({"data_vendors": {"news_data": "akshare_news"}})
            result = interface.route_to_vendor(
                "get_news", "000977.SZ", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "akshare-news-ok")

    def test_a_share_news_prefers_akshare_news(self):
        calls = []

        def akshare_news(*args):
            calls.append("akshare_news")
            return "akshare-news-ok"

        def yfinance_news(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"yfinance": yfinance_news, "akshare_news": akshare_news}},
            clear=False,
        ):
            set_config({"data_vendors": {"news_data": "yfinance,akshare_news"}})
            result = interface.route_to_vendor(
                "get_news", "000966.SZ", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "akshare-news-ok")
        self.assertEqual(calls, ["akshare_news"])

    def test_us_news_keeps_english_vendor_first(self):
        calls = []

        def akshare_news(*args):
            calls.append("akshare_news")
            return "akshare-news-ok"

        def yfinance_news(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"akshare_news": akshare_news, "yfinance": yfinance_news}},
            clear=False,
        ):
            set_config({"data_vendors": {"news_data": "akshare_news,yfinance"}})
            result = interface.route_to_vendor(
                "get_news", "NVDA", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "yfinance-ok")
        self.assertEqual(calls, ["yfinance"])

    def test_no_data_available_falls_back_to_next_news_vendor(self):
        calls = []

        def akshare_news(*args):
            calls.append("akshare_news")
            return "NO_DATA_AVAILABLE: no Chinese news"

        def yfinance_news(*args):
            calls.append("yfinance")
            return "yfinance-ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"akshare_news": akshare_news, "yfinance": yfinance_news}},
            clear=False,
        ):
            set_config({"data_vendors": {"news_data": "akshare_news,yfinance"}})
            result = interface.route_to_vendor(
                "get_news", "000966.SZ", "2026-06-09", "2026-06-10"
            )
        self.assertEqual(result, "yfinance-ok")
        self.assertEqual(calls, ["akshare_news", "yfinance"])


if __name__ == "__main__":
    unittest.main()
