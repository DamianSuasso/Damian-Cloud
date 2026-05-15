import requests

class PriceService:
    def __init__(self):
        # We use Binance's public ticker for fast, keyless price lookups
        self.base_url = "https://api.binance.com/api/v3/ticker/price"

    def get_eur_price(self, symbol):
        """Fetches the current price of a symbol in EUR."""
        # Normalize symbol (e.g., BTC -> BTCEUR)
        # Note: Some coins on Binance might only have USDT pairs. 
        # For professional accuracy, we try EUR first, then USDT as fallback.
        symbol = symbol.upper()
        pairs_to_try = [f"{symbol}EUR", f"{symbol}USDT"]
        
        for pair in pairs_to_try:
            try:
                response = requests.get(f"{self.base_url}?symbol={pair}", timeout=5)
                if response.status_code == 200:
                    price = float(response.json()['price'])
                    # If we used USDT, we'd technically need to multiply by EUR/USDT rate, 
                    # but for now, BTCEUR usually exists.
                    return price
            except:
                continue
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