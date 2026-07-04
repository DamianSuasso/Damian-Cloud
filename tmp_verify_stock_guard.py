from unittest.mock import patch
from Portfolio_tracker.utils.stock_price_service import StockPriceService

service = StockPriceService()
with patch.object(service, '_resolve_market_ticker', return_value=''):
    service.fetch_and_cache_historical_prices('US25058X1054', start_date='2023-01-01')
print('empty-return-guard-ok')
