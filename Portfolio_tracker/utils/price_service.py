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

    def seed_historical_prices_bulk(self, symbol, start_year=2020):
        """
        🚀 INTUITIVE BULK SEEDER V4:
        1. Checks database first to avoid duplicate API requests.
        2. Fetches BOTH native EUR and USDT daily charts from Binance in parallel.
        3. Only uses the EURUSDT forex cross-rate as a fallback calculation if 
           one of the markets is missing a specific date.
        """
        symbol = symbol.upper().strip()
        if symbol in ['EUR', 'USDT']: return
        
        # --- STEP 1: PRE-FLIGHT DATABASE CACHE CHECK ---
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*), MAX(date) 
                FROM historical_prices 
                WHERE asset = ? AND price_eur > 0
            """, (symbol,))
            
            row = cursor.fetchone()
            conn.close()
            
            # 🔧 FIX: Explicit fallback handling if row is empty or un-iterable
            if row and len(row) == 2:
                cached_count = row[0] if row[0] is not None else 0
                max_date_str = row[1]  # This will be a string like '2026-06-12' or None
            else:
                cached_count = 0
                max_date_str = None
            
            # Target fresh baseline (e.g., must have historical data reaching up to 2 days ago)
            two_days_ago = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
            
            # Validate row volume AND timeline coverage matches our 2026 window
            if cached_count > 100 and max_date_str and max_date_str >= two_days_ago:
                print(f"✅ Cache verified for {symbol} ({cached_count} days found up to {max_date_str}). Skipping bulk download.")
                return
            else:
                # Provide a clear, descriptive reason in the console logs
                if not max_date_str:
                    reason = "Database empty / No records found"
                elif max_date_str < two_days_ago:
                    reason = f"Cache stale (Ends on {max_date_str}, needs to reach {two_days_ago})"
                else:
                    reason = f"Insufficient history (Only {cached_count} rows found)"
                    
                print(f"🔄 Cache refresh required for {symbol} ({reason}). Initiating synchronization...")
                
        except Exception as e:
            print(f"⚠️ Pre-flight cache check failed: {e}")

        # --- STEP 2: DETERMINE NETWORK PAIRS ---
      
        start_dt = datetime(start_year, 1, 1)
        ms_start_timestamp = int(start_dt.timestamp() * 1000)

        params = {'interval': '1d', 'startTime': ms_start_timestamp, 'limit': 1000}
        eur_candles_map = {}
        usdt_candles_map = {}
        all_dates = set()
  
        # 🇪🇺 Fetch Native EUR Chart Data
        try:
            res_eur = requests.get(self.kline_url, params={**params, 'symbol': f"{symbol}EUR"}, timeout=10)
            if res_eur.status_code == 200 and res_eur.json():
                for c in res_eur.json():
                    d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                    eur_candles_map[d] = float(c[4])
                    all_dates.add(d)
        except Exception:
            pass
  
        # 🇺🇸 Fetch Native USDT Chart Data
        try:
            res_usdt = requests.get(self.kline_url, params={**params, 'symbol': f"{symbol}USDT"}, timeout=10)
            if res_usdt.status_code == 200 and res_usdt.json():
                for c in res_usdt.json():
                    d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                    usdt_candles_map[d] = float(c[4])
                    all_dates.add(d)
        except Exception:
            pass
                
        if not all_dates:
            print(f"🔄 Binance missing {symbol}. Route diversion to public CoinGecko engine...")
            try:
                # 🔐 Extract the credential cleanly from your environment variables
                coingecko_api_key = os.getenv("COINGECKO_API_KEY")
                if not coingecko_api_key:
                    print("❌ Aborted: COINGECKO_API_KEY environment variable missing from .env file.")
                    return
                
                # Map standard tickers to CoinGecko API IDs
                gecko_id_map = {
                    "LMWR": "limewire",
                    "TRUMP": "official-trump-token"  # Example if a meme/minor token missing on Binance CEX
                }
                gecko_id = gecko_id_map.get(symbol, symbol.lower())
                
                # Verified Public API URL Route Structure
                url = f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart"
                cg_params = {
                    'vs_currency': 'usd', 
                    'days': '365', 
                    'interval': 'daily',
                    'x_cg_demo_api_key': coingecko_api_key  # Pass key as parameter
                }
                
                res = requests.get(url, params=cg_params, timeout=10)
                
                if res.status_code == 200:
                    cg_data = res.json()
                    prices_array = cg_data.get("prices", [])  # Returns list of [timestamp, price]
                    
                    # Fetch live or static backup forex cross rate for conversion
                    # Since CoinGecko data handles USD/USDT, we want to pop native EUR lines too
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    inserted_count = 0
                    
                    for item in prices_array:
                        ts_ms = item[0]
                        price_usdt = float(item[1])
                        candle_date = datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
                        
                        # Fallback calculation to store twin-fiat row
                        price_eur = price_usdt / 1.08  
                        
                        cursor.execute("""
                            INSERT OR REPLACE INTO historical_prices (asset, date, price_eur, price_usdt)
                            VALUES (?, ?, ?, ?)
                        """, (symbol, candle_date, price_eur, price_usdt))
                        inserted_count += 1
                        
                    conn.commit()
                    conn.close()
                    print(f"✨ Successfully supplemented {inserted_count} historical rows for {symbol} via CoinGecko!")
                    return
                else:
                    print(f"❌ CoinGecko verification route failed. Status: {res.status_code}")
            except Exception as e:
                print(f"❌ Comprehensive backup engine exception: {e}")
                
            print(f"❌ No historical data found on Binance or CoinGecko for {symbol}.")
            return

        # --- STEP 3: HISTORICAL CROSS-RATE MAP (POPULATED ALWAYS) ---
        raw_eur_usdt_history = {}
        # Lazy evaluation: Only hit the FX pair if there's a market discrepancy to resolve
        if len(eur_candles_map) != len(usdt_candles_map):
            try:
                print(f"🔀 Data gap detected between markets. Fetching EURUSDT cross-rates for calculations...")
                fx_res = requests.get(self.kline_url, params={**params, 'symbol': 'EURUSDT'}, timeout=10)
                if fx_res.status_code == 200:
                    for c in fx_res.json():
                        d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                        raw_eur_usdt_history[d] = float(c[4])
            except Exception as e:
                print(f"⚠️ Failed to pull backup forex cross-rates: {e}")

        # --- STEP 4: TWIN-CURRENCY CALCULATIONS & DATABASE WRITE ---
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            inserted_count = 0
            gap_logged = False

            for candle_date in sorted(list(all_dates)):
                close_price_eur = eur_candles_map.get(candle_date, 0.0)
                close_price_usdt = usdt_candles_map.get(candle_date, 0.0)
                
                # If a gap exists for this specific day, resolve it mathematically
                if close_price_eur == 0.0 or close_price_usdt == 0.0:
                    eur_usdt_rate = raw_eur_usdt_history.get(candle_date, 1.08)
                    
                    if close_price_eur == 0.0 and close_price_usdt > 0.0:
                        if not gap_logged:
                            # We only have USDT -> derive EUR
                            print(f"   ℹ️ [{candle_date}] Missing {symbol}EUR market. Deriving EUR from native USDT data...")
                            gap_logged = True
                        
                        close_price_eur = close_price_usdt / eur_usdt_rate if eur_usdt_rate > 0 else close_price_usdt * 0.92
                    
                    elif close_price_usdt == 0.0 and close_price_eur > 0.0:
                        if not gap_logged:
                            # We only have EUR -> derive USDT
                            print(f"   ℹ️ [{candle_date}] Missing {symbol}USDT market. Deriving USDT from native EUR data...")
                            gap_logged = True
                        
                        close_price_usdt = close_price_eur * eur_usdt_rate

                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, date, price_eur, price_usdt)
                    VALUES (?, ?, ?, ?)
                """, (symbol, candle_date, close_price_eur, close_price_usdt))
                inserted_count += 1
                
            conn.commit()
            conn.close()
            print(f"✨ Successfully synchronized {inserted_count} clean dual-market rows for {symbol}!")     
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

    def get_historical_prices(self, symbol, iso_timestamp):
        """
        Fetches the historical price of a coin at a specific time.
        iso_timestamp example: '2026-01-15T12:00:00.000Z'
        """
        symbol = symbol.upper()
        if symbol == 'EUR': return {'price_eur': 1.0, 'price_usdt': 1.08}
        if symbol == 'USD' or symbol == 'USDT': return {'price_eur': 0.92, 'price_usdt': 1.0}
        
        date_key = iso_timestamp[:10]
        
        # 1. 🗄️ Isolated Cache Read (Open, Read, Close Immediately)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price_eur, price_usdt FROM historical_prices WHERE asset = ? AND date = ?", 
                (symbol, date_key)
            )
            row = cursor.fetchone()
            conn.close() # Free the file lock immediately
            if row and row[0] is not None and row[1] is not None:
                return {'price_eur': float(row[0]), 'price_usdt': float(row[1])}
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
            return 0.0, 0.0

        # 3. 🌐 API Lookup Section (Completely decoupled from SQLite)        
        fetched_price_eur = 0.0
        fetched_price_usdt = 0.0
        
        try:
            # 🇪🇺 Step A: Try to fetch native EUR pair directly
            res_eur = requests.get(f"{self.kline_url}?symbol={symbol}EUR&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
            if res_eur.status_code == 200 and len(res_eur.json()) > 0:
                fetched_price_eur = float(res_eur.json()[0][4])

            # 🇺🇸 Step B: Try to fetch native USDT pair directly
            res_usdt = requests.get(f"{self.kline_url}?symbol={symbol}USDT&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
            if res_usdt.status_code == 200 and len(res_usdt.json()) > 0:
                fetched_price_usdt = float(res_usdt.json()[0][4])

            # 🔀 Step C: Fallback Calculation Math (Only if ONE of them is missing)
            if fetched_price_eur > 0.0 or fetched_price_usdt > 0.0:
                # We only need the forex cross-rate if we have a blind spot
                if fetched_price_eur == 0.0 or fetched_price_usdt == 0.0:
                    fx_res = requests.get(f"{self.kline_url}?symbol=EURUSDT&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
                    eur_usdt_rate = float(fx_res.json()[0][4]) if (fx_res.status_code == 200 and len(fx_res.json()) > 0) else 1.08
                    
                    if fetched_price_eur == 0.0:  # We only have USDT, calculate EUR
                        fetched_price_eur = fetched_price_usdt / eur_usdt_rate
                    elif fetched_price_usdt == 0.0:  # We only have EUR, calculate USDT
                        fetched_price_usdt = fetched_price_eur * eur_usdt_rate
        except Exception as e:
            print(f"⚠️ Binance network call failed for {symbol}: {e}")

                # 4. 🔄 COINGECKO ROUTE DIVERSION (Executed if Binance returned completely empty data)
        if fetched_price_eur == 0.0 and fetched_price_usdt == 0.0:
            try:
                coingecko_api_key = os.getenv("COINGECKO_API_KEY")
                if coingecko_api_key:
                    gecko_id_map = {"LMWR": "limewire", "TRUMP": "official-trump-token"}
                    gecko_id = gecko_id_map.get(symbol, symbol.lower())
                    
                    # Call CoinGecko's explicit daily historical chart endpoint via demo channel
                    cg_url = f"https://api-demo.coingecko.com/api/v3/coins/{gecko_id}/market_chart"
                    cg_params = {'vs_currency': 'usd', 'days': '365', 'interval': 'daily', 'x_cg_demo_api_key': coingecko_api_key}
                    
                    res = requests.get(cg_url, params=cg_params, timeout=5)
                    if res.status_code == 200:
                        prices_array = res.json().get("prices", [])
                        # Find the closest entry matching our target date string
                        for item in prices_array:
                            item_date = datetime.utcfromtimestamp(item[0] / 1000).strftime("%Y-%m-%d")
                            if item_date == date_key:
                                fetched_price_usdt = float(item[1])
                                
                                # Extract accurate cross rate from local DB for true EUR valuation balance
                                try:
                                    conn = sqlite3.connect(self.db_path)
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT price_usdt / price_eur FROM historical_prices WHERE asset = 'BTC' AND date = ? AND price_eur > 0", (date_key,))
                                    db_rate = cursor.fetchone()
                                    conn.close()
                                    eur_usdt_rate = float(db_rate[0]) if db_rate else 1.08
                                except Exception:
                                    eur_usdt_rate = 1.08
                                    
                                fetched_price_eur = fetched_price_usdt / eur_usdt_rate
                                break
            except Exception as e:
                print(f"⚠️ Secondary CoinGecko track engine exception for {symbol}: {e}")

        # 5. 💾 Isolated Cache Write (Populates both columns while keeping return signatures intact)
        if fetched_price_eur > 0.0:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, date, price_eur, price_usdt)
                    VALUES (?, ?, ?, ?)
                """, (symbol, date_key, fetched_price_eur, fetched_price_usdt))
                conn.commit()
                conn.close() 
            except Exception as e:
                print(f"⚠️ Failed to write fallback cache to database: {e}")
                
        # Keeps your historical timeline loop perfectly happy without signature changes
        return {'price_eur': fetched_price_eur, 'price_usdt': fetched_price_usdt}