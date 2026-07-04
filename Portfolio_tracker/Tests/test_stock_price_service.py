from datetime import date, datetime
from unittest.mock import patch

from Portfolio_tracker.utils.stock_price_service import StockPriceService


def test_parse_date_accepts_strings_and_datetime_objects():
    service = StockPriceService()

    assert service._parse_date("2025-01-10") == date(2025, 1, 10)
    assert service._parse_date(date(2025, 1, 10)) == date(2025, 1, 10)
    assert service._parse_date(datetime(2025, 1, 10, 12, 30, 0)) == date(2025, 1, 10)


def test_fetch_and_cache_skips_unresolved_tickers():
    service = StockPriceService()

    with patch.object(service, "_resolve_market_ticker", return_value=""), patch(
        "Portfolio_tracker.utils.stock_price_service.requests.get",
        side_effect=AssertionError("requests.get should not be called for unresolved symbols"),
    ):
        service.fetch_and_cache_historical_prices("US25058X1054", start_date="2023-01-01")


def test_fetch_and_cache_skips_isin_like_identifiers():
    service = StockPriceService()

    with patch.object(service, "_resolve_market_ticker", return_value="US25058X1054"), patch(
        "Portfolio_tracker.utils.stock_price_service.requests.get",
        side_effect=AssertionError("requests.get should not be called for ISIN-like identifiers"),
    ):
        service.fetch_and_cache_historical_prices("US25058X1054", start_date="2023-01-01")
