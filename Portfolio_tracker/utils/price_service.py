import requests
from datetime import datetime

class PriceService:
    def __init__(self):
        # We use Binance's public ticker for fast, keyless price lookups
        self.base_url = "https://api.binance.com/api/v3/ticker/price"
        self.kline_url = "https://api.binance.com/api/v3/klines"

    def get_eur_price(self, symbol):
        """Fetches the current price of a symbol in EUR."""
        symbol = symbol.upper()
        if symbol == 'EUR': return 1.0
        pairs_to_try = [f"{symbol}EUR", f"{symbol}USDT"]
        
        for pair in pairs_to_try:
            try:
                response = requests.get(f"{self.base_url}?symbol={pair}", timeout=5)
                if response.status_code == 200:
                    return float(response.json()['price'])
            except:
                continue
        return 0.0

    def get_historical_eur_price(self, symbol, iso_timestamp):
        """
        Fetches the historical price of a coin at a specific time.
        iso_timestamp example: '2026-01-15T12:00:00.000Z'
        """
        symbol = symbol.upper()
        if symbol == 'EUR': return 1.0
        
        # Convert ISO timestamp string to milliseconds for Binance
        try:
            # Handle standard ISO formats
            clean_ts = iso_timestamp.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_ts)
            ms_timestamp = int(dt.timestamp() * 1000)
        except Exception as e:
            return 0.0

        pair = f"{symbol}EUR"
        # We query a 1-minute window starting at our target timestamp
        params = {
            'symbol': pair,
            'interval': '1m',
            'startTime': ms_timestamp,
            'limit': 1
        }
        
        try:
            res = requests.get(self.kline_url, params=params, timeout=5)
            if res.status_code == 200 and len(res.json()) > 0:
                # Index 4 is the "Close Price" of that 1-minute candle
                return float(res.json()[0][4])
        except:
            pass
        return 0.0
    
    def valuate_portfolio(self, portfolio_dict):
        """
        Takes a dict like {'BTC': 0.5, 'ETH': 1.2} 
        Returns a dict with quantities and EUR values.
        """
        valued_data = {}
        for coin, qty in portfolio_dict.items():
            if isinstance(qty, (int, float)) and qty > 0:
                price = self.get_eur_price(coin)
                valued_data[coin] = {
                    'qty': qty,
                    'price': price,
                    'total_eur': qty * price
                }
            else:
                valued_data[coin] = {'qty': qty, 'price': 0, 'total_eur': 0}
        return valued_data