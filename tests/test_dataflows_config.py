"""Config isolation: get/set must not leak nested-dict references."""

import copy
import importlib
import os
import unittest

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import get_config, set_config


@pytest.mark.unit
class DataflowsConfigIsolationTests(unittest.TestCase):
    def setUp(self):
        self._vendor_env_keys = (
            default_config._DATA_VENDOR_ALL_ENV,
            *default_config._DATA_VENDOR_ENV_OVERRIDES,
        )
        self._saved_vendor_env = {
            key: os.environ.get(key) for key in self._vendor_env_keys
        }
        for key in self._vendor_env_keys:
            os.environ.pop(key, None)
        importlib.reload(default_config)
        set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))

    def tearDown(self):
        for key in self._vendor_env_keys:
            os.environ.pop(key, None)
        for key, value in self._saved_vendor_env.items():
            if value is not None:
                os.environ[key] = value
        importlib.reload(default_config)

    def test_get_config_returns_deep_copy(self):
        cfg = get_config()
        cfg["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        cfg["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "tushare,akshare,yfinance")
        self.assertNotIn("get_stock_data", fresh["tool_vendors"])

    def test_set_config_does_not_alias_caller_nested_dicts(self):
        custom = copy.deepcopy(default_config.DEFAULT_CONFIG)
        custom["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        custom["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        set_config(custom)

        custom["data_vendors"]["core_stock_apis"] = "yfinance"
        custom["tool_vendors"]["get_stock_data"] = "yfinance"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")

    def test_partial_nested_update_preserves_existing_defaults(self):
        set_config(
            {
                "data_vendors": {
                    "core_stock_apis": "alpha_vantage",
                }
            }
        )

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(fresh["data_vendors"]["technical_indicators"], "tushare,akshare,yfinance")
        self.assertEqual(fresh["data_vendors"]["fundamental_data"], "tushare,yfinance")
        self.assertEqual(fresh["data_vendors"]["news_data"], "akshare_news,yfinance")

    def test_nested_dict_updates_merge_one_level_deep(self):
        set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
        set_config({"tool_vendors": {"get_news": "alpha_vantage"}})

        fresh = get_config()
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_news"], "alpha_vantage")
