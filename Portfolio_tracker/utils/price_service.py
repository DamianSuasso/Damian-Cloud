import os
import requests
from datetime import datetime, timedelta
import sqlite3

class PriceService:
    def __init__(self, db_name="sentinel_vault.db"):
        self.base_url = "https://api.binance.com/api/v3/ticker/price"
        self.kline_url = "https://api.binance.com/api/v3/klines"

        utils_dir = os.path.dirname(os.path.abspath(__file__))
        portfolio_tracker_dir = os.path.dirname(utils_dir)
        db_dir = os.path.join(portfolio_tracker_dir, "database")
        self.db_path = os.path.join(db_dir, db_name)
        self._init_cache_table()

    def _init_cache_table(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_prices (
                    asset TEXT,
                    date TEXT,
                    price_eur REAL,
                    PRIMARY KEY (asset, date)
                );
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Warning: Could not initialize price cache storage: {e}")

    def seed_historical_prices_bulk(self, symbol, start_year=2020):
        """
        🚀 RESILIENT BULK SEEDER: Fetches up to 1000 daily close prices.
        Automatically falls back to USDT pairs if a direct EUR pair doesn't exist on Binance.
        """
        symbol = symbol.upper()
        if symbol == 'EUR': return
        
        # 1. Determine pairs to try (Direct EUR first, then USDT stablecoin bridge)
        pairs_to_try = [f"{symbol}EUR", f"{symbol}USDT"]
        candles = None
        used_pair = None
        
        start_dt = datetime(start_year, 1, 1)
        ms_start_timestamp = int(start_dt.timestamp() * 1000)
        
        for pair in pairs_to_try:
            params = {
                'symbol': pair,
                'interval': '1d',
                'startTime': ms_start_timestamp,
                'limit': 1000
            }
            try:
                res = requests.get(self.kline_url, params=params, timeout=10)
                if res.status_code == 200:
                    candles = res.json()
                    if candles:
                        used_pair = pair
                        break # Success! Break out of the fallback loop
            except Exception:
                continue # Try the next pair if network errors happen
                
        if not candles:
            print(f"❌ Could not find active Binance historical charts for {symbol} in EUR or USDT.")
            return

        # 2. If we had to use USDT, fetch the current EUR/USDT cross-rate to convert it back
        eur_conversion_factor = 1.0
        if "USDT" in used_pair:
            # We fetch a ballpark conversion rate (1 / EURUSDT) to normalize the history to EUR
            try:
                usdt_eur_res = requests.get(f"{self.base_url}?symbol=EURUSDT", timeout=5)
                if usdt_eur_res.status_code == 200:
                    # If 1 EUR = 1.08 USDT, then 1 USDT = 1 / 1.08 EUR
                    eur_conversion_factor = 1.0 / float(usdt_eur_res.json()['price'])
                    print(f"🔀 Using USDT Bridge for {symbol}. Applying current conversion factor (1 USDT ≈ {eur_conversion_factor:.4f} EUR)")
            except:
                # Fallback to a hardcoded baseline if the cross-rate lookup fails completely
                eur_conversion_factor = 0.92 

        # 3. Commit the converted history straight into your local cache database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            inserted_count = 0
            for candle in candles:
                candle_ms = candle[0]
                candle_date = datetime.utcfromtimestamp(candle_ms / 1000).strftime("%Y-%m-%d")
                
                # Multiply the raw close price by our conversion factor
                close_price_eur = float(candle[4]) * eur_conversion_factor
                
                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, date, price_eur)
                    VALUES (?, ?, ?)
                """, (symbol, candle_date, close_price_eur))
                inserted_count += 1
                
            conn.commit()
            conn.close()
            print(f"✨ Successfully cached {inserted_count} historical daily points for {symbol} via {used_pair}!")
        except Exception as e:
            print(f"⚠️ Bulk seeding error writing to cache for {symbol}: {e}")

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
        
        date_key = iso_timestamp[:10]
        
        # 1. 🗄️ Isolated Cache Read (Open, Read, Close Immediately)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price_eur FROM historical_prices WHERE asset = ? AND date = ?", 
                (symbol, date_key)
            )
            row = cursor.fetchone()
            conn.close() # Free the file lock immediately
            if row:
                return row[0]  # 🔥 Local DB hit: takes microseconds
        except Exception as e:
            print(f"⚠️ Cache read error: {e}")
            
        # 2. 💥 CRITICAL CACHE MISS
        print(f"💥 CACHE MISS! Hitting Binance API for {symbol} on {date_key}...")
        
        # Convert timestamp safely without risking connection state leaks
        try:
            clean_ts = iso_timestamp.replace('Z', '+00:00')
            parent_dt = datetime.fromisoformat(clean_ts)
            ms_timestamp = int(parent_dt.timestamp() * 1000)
        except Exception as e:
            print(f"⚠️ Timestamp parsing failed for {iso_timestamp}: {e}")
            return 0.0

        # 3. 🌐 API Lookup Section (Completely decoupled from SQLite)
        pair = f"{symbol}EUR"
        params = {
            'symbol': pair,
            'interval': '1m',
            'startTime': ms_timestamp,
            'limit': 1
        }
        
        fetched_price = 0.0
        try:
            res = requests.get(self.kline_url, params=params, timeout=5)
            if res.status_code == 200 and len(res.json()) > 0:
                fetched_price = float(res.json()[0][4])
            else:
                # 🔀 Stablecoin Fallback Bridge for tokens without direct EUR pairs
                alt_res = requests.get(f"{self.kline_url}?symbol={symbol}USDT&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
                if alt_res.status_code == 200 and len(alt_res.json()) > 0:
                    fetched_price = float(alt_res.json()[0][4]) * 0.92  # Ballpark EUR conversion
        except Exception as e:
            print(f"⚠️ Binance network call failed for {symbol}: {e}")
            
        # 4. 💾 Isolated Cache Write (Only open connection if we actually have data to write)
        if fetched_price > 0.0:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, date, price_eur)
                    VALUES (?, ?, ?)
                """, (symbol, date_key, fetched_price))
                conn.commit()
                conn.close() # Keep it clean
            except Exception as e:
                print(f"⚠️ Failed to write fallback cache to database: {e}")
                
        return fetched_price