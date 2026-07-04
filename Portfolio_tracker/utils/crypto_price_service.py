import os
import csv
import sqlite3
import requests
from datetime import datetime, timedelta


class Crypto_PriceService:
    def __init__(self, db_name="sentinel_vault.db"):
        self.base_url = "https://api.binance.com/api/v3/ticker/price"
        self.kline_url = "https://api.binance.com/api/v3/klines"

        utils_dir = os.path.dirname(os.path.abspath(__file__))
        portfolio_tracker_dir = os.path.dirname(utils_dir)
        db_dir = os.path.join(portfolio_tracker_dir, "database")
        self.db_path = os.path.join(db_dir, db_name)

    def _check_cache_freshness(self, symbol, start_year):
        """Internal helper to analyze database content against target configurations."""
        default_start = f"{start_year}-01-01"
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), MAX(date) 
                FROM historical_prices 
                WHERE asset = ? AND asset_type = 'CRYPTO' AND price_eur > 0
            """, (symbol,))
            row = cursor.fetchone()
            conn.close()
            
            if row and len(row) == 2:
                cached_count = row[0] if row[0] is not None else 0
                max_date_str = row[1]
            else:
                cached_count = 0
                max_date_str = None
                
            sixty_days_ago = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")
            
            if cached_count > 100 and max_date_str and max_date_str >= sixty_days_ago:
                print(f"✅ [Crypto_PriceService] Cache verified for {symbol} (Up to {max_date_str}). Skipping bulk download.")
                return False, None
                
            if max_date_str:
                last_dt = datetime.strptime(max_date_str, "%Y-%m-%d")
                next_start_date = (last_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                reason = f"Cache ends on {max_date_str}, resuming forward..."
            else:
                next_start_date = default_start
                reason = f"No local records found, seeding from {default_start}..."
                
            print(f"🔄 [Crypto_PriceService] Cache synchronization required for {symbol} ({reason})")
            return True, next_start_date
            
        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Pre-flight cache check calculation exception: {e}")
            return True, default_start

    def _fetch_coingecko_fallback(self, symbol, date_key=None):
        """
        Unified CoinGecko engine routing.
        1. Bulk Seed Mode (date_key=None): Pulls standard trailing 365 days.
        2. Pinpoint Mode (date_key="YYYY-MM-DD"): Uses the /range endpoint to pull a 
        targeted 5-day window around the historical event.
        3. Emergency Mode: Fall back to local CSV parsing if API fails/is constrained.
        """

        # --- STEP 1: DEFINE LOCAL CSV EMERGENCY ENGINE ---
        def parse_local_csv_fallback(target_date_str):
            utils_dir = os.path.dirname(os.path.abspath(__file__))
            portfolio_tracker_dir = os.path.dirname(utils_dir)
            
            # 2. Point directly to the correct absolute path inside Portfolio_tracker/imports/
            csv_path = os.path.join(portfolio_tracker_dir, "imports", "lmwr-usd-max.csv")
            if symbol.upper() != "LMWR" or not os.path.exists(csv_path):
                return None

            print(f"📂 [Crypto_PriceService] API boundary/limit hit. Activating local CSV look-up engine for {symbol} on {target_date_str}...")
            try:
                target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
                best_price = None
                smallest_delta = float('inf')
                matched_date = ""

                with open(csv_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)  # Expected columns: snapped_at, price, market_cap, total_volume
                    for row in reader:
                        # Strip the timezone text '00:00:00 UTC' to extract date
                        raw_date = row['snapped_at'].split(" ")[0]
                        row_dt = datetime.strptime(raw_date, "%Y-%m-%d")
                        
                        delta = abs((target_dt - row_dt).total_seconds())
                        if delta < smallest_delta:
                            smallest_delta = delta
                            best_price = float(row['price'])
                            matched_date = raw_date

                # Allow a max separation margin of 36 hours for daily charts
                if best_price is not None and smallest_delta < 130000:
                    print(f"🎯 [Crypto_PriceService] Local CSV Match Isolated! target: {target_date_str} | row: {matched_date} | price: ${best_price:.4f}")
                    return best_price
                    
                print(f"❌ [Crypto_PriceService] Date {target_date_str} falls outside the boundaries of the local CSV history file.")
                return None
            except Exception as csv_err:
                print(f"⚠️ [Crypto_PriceService] Failed reading from backup file {csv_path}: {csv_err}")
                return None
        
        coingecko_api_key = os.getenv("COINGECKO_API_KEY")
        if not coingecko_api_key:
            print("❌ [Crypto_PriceService] Aborted: COINGECKO_API_KEY environment variable missing from .env file.")
            if date_key:
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)
            return None if date_key else False

        gecko_id_map = {"LMWR": "limewire-token",
                        "GRAM": "gram"}
        gecko_id = gecko_id_map.get(symbol, symbol.lower())
        
        # --- DYNAMIC ENDPOINT DISPATCH ---
        if date_key:
            target_dt = datetime.strptime(date_key, "%Y-%m-%d")
            start_dt = target_dt - timedelta(days=2)
            end_dt = target_dt + timedelta(days=3)
            
            url = f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart/range"
            cg_params = {
                'vs_currency': 'usd',
                'from': int(start_dt.timestamp()),
                'to': int(end_dt.timestamp()),
                'x_cg_demo_api_key': coingecko_api_key
            }
        else:
            url = f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart"
            cg_params = {
                'vs_currency': 'usd', 
                'days': '365', 
                'interval': 'daily',
                'x_cg_demo_api_key': coingecko_api_key
        }
        
        try:
            res = requests.get(url, params=cg_params, timeout=10)
            if res.status_code != 200:
                print(f"⚠️ [Crypto_PriceService] CoinGecko API returned error status: {res.status_code}.")
                if date_key:
                    csv_price = parse_local_csv_fallback(date_key)
                    if csv_price is not None:
                        return self._package_price_with_cross_rate(csv_price, date_key)
                return {'price_eur': 0.0, 'price_usdt': 0.0} if date_key else False

            prices_array = res.json().get("prices", [])
            
            # --- FLAVOR 1: PINPOINT TARGET DATE RUN ---
            if date_key:
                target_ts = target_dt.timestamp() # Target timestamp in seconds
                best_match = None
                smallest_delta = float('inf')

                print(f"🕵️ [Crypto_PriceService] Scanning CoinGecko dataset ({len(prices_array)} entries) for closest match to {date_key}...")

                for item in prices_array:
                    item_ts = item[0] / 1000  # Convert ms to seconds
                    delta = abs(target_ts - item_ts)
                    if delta < smallest_delta:
                        smallest_delta = delta
                        best_match = item

                # 24 hours is 86400 seconds. Allow a 36-hour window for safety margins
                if best_match and smallest_delta < 130000:
                    price_usdt = float(best_match[1])
                    found_date = datetime.utcfromtimestamp(best_match[0] / 1000).strftime("%Y-%m-%d")
                    print(f"🎯 [Crypto_PriceService] Match isolated via API range! Target: {date_key} | Found: {found_date} | Price: ${price_usdt:.4f}")
                    return self._package_price_with_cross_rate(price_usdt, date_key)
                    # Gather actual cross-rate calculation parameters out of the DB cache
                
                # API range array was returned empty or missed the date window; try local file
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)

                print(f"❌ [Crypto_PriceService] Failed to locate a reliable historical window across API or local CSV for {symbol} on {date_key}.")
                return {'price_eur': 0.0, 'price_usdt': 0.0}

            # --- FLAVOR 2: BULK SEED CACHE COMMIT RUN ---
            else:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                inserted_count = 0
                
                for item in prices_array:
                    price_usdt = float(item[1])
                    candle_date = datetime.utcfromtimestamp(item[0] / 1000).strftime("%Y-%m-%d")
                    price_eur = price_usdt / 1.08  # Default static calculation for generic bulk fills
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                        VALUES (?, 'CRYPTO', ?, ?, ?)
                    """, (symbol, candle_date, price_eur, price_usdt))
                    inserted_count += 1
                    
                conn.commit()
                conn.close()
                print(f"✨ [Crypto_PriceService] Successfully supplemented {inserted_count} historical rows for {symbol} via CoinGecko!")
                return True

        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Core loop exception: {e}")
            if date_key:
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)
            return {'price_eur': 0.0, 'price_usdt': 0.0} if date_key else False

    def _package_price_with_cross_rate(self, price_usdt, date_key):
        """Helper method to isolate the database cross-rate calculation logic."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT price_usdt / price_eur FROM historical_prices WHERE asset = 'BTC' AND date = ? AND price_eur > 0", (date_key,))
            db_rate = cursor.fetchone()
            conn.close()
            eur_usdt_rate = float(db_rate[0]) if db_rate else 1.08
        except Exception:
            eur_usdt_rate = 1.08
            
        return {'price_eur': price_usdt / eur_usdt_rate, 'price_usdt': price_usdt}

    def seed_historical_prices_bulk(self, symbol, start_year=2023):
        symbol = symbol.upper().strip()
        if symbol in ['EUR', 'USDT']: 
            return
        
        needs_sync, sync_start_str = self._check_cache_freshness(symbol, start_year)
        if not needs_sync:
            return

        # --- TICKER MIGRATION SPLIT LOGIC ---
        # If tracking MATIC or POL, we fetch both variants to build a unified timeline
        search_symbols = [symbol]
        if symbol in ['MATIC', 'POL']:
            search_symbols = ['MATIC', 'POL']
        elif symbol in ['FTM', 'S']:
            search_symbols = ['FTM', 'S']

        try:
            start_dt = datetime.strptime(sync_start_str, "%Y-%m-%d")
            ms_start_timestamp = int(start_dt.timestamp() * 1000)
        except Exception as e:
            ms_start_timestamp = int(datetime(start_year, 1, 1).timestamp() * 1000)

        params = {'interval': '1d', 'startTime': ms_start_timestamp, 'limit': 1000}
        eur_candles_map = {}
        usdt_candles_map = {}
        all_dates = set()

        # Loop through both the old and new ticker variations if necessary
        for target_ticker in search_symbols:
            # 🇪🇺 Fetch Native EUR Chart Data
            try:
                res_eur = requests.get(self.kline_url, params={**params, 'symbol': f"{target_ticker}EUR"}, timeout=10)
                if res_eur.status_code == 200 and res_eur.json():
                    for c in res_eur.json():
                        d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                        # Enforce boundary checking so old data doesn't skew weird overlap mappings
                        if target_ticker == 'MATIC' and d >= '2024-09-04': continue
                        if target_ticker == 'POL' and d < '2024-09-04': continue
                        if target_ticker == 'FTM' and d >= '2025-01-13': continue
                        if target_ticker == 'S' and d < '2025-01-13': continue
                        
                        eur_candles_map[d] = float(c[4])
                        all_dates.add(d)
            except Exception:
                pass
      
            # 🇺🇸 Fetch Native USDT Chart Data
            try:
                res_usdt = requests.get(self.kline_url, params={**params, 'symbol': f"{target_ticker}USDT"}, timeout=10)
                if res_usdt.status_code == 200 and res_usdt.json():
                    for c in res_usdt.json():
                        d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                        if target_ticker == 'MATIC' and d >= '2024-09-04': continue
                        if target_ticker == 'POL' and d < '2024-09-04': continue
                        if target_ticker == 'FTM' and d >= '2025-01-13': continue
                        if target_ticker == 'S' and d < '2025-01-13': continue 

                        usdt_candles_map[d] = float(c[4])
                        all_dates.add(d)
            except Exception:
                pass
                
        # --- CLEAN ROUTE DELEGATION ---
        if not all_dates:
            print(f"🔄 [Crypto_PriceService] Binance missing {symbol}. Route diversion to public CoinGecko engine...")
            if not self._fetch_coingecko_fallback(symbol):
                print(f"❌ [Crypto_PriceService] No historical data found on Binance or CoinGecko for {symbol}.")
            return

        # --- STEP 3: HISTORICAL CROSS-RATE MAP ---
        raw_eur_usdt_history = {}
        if len(eur_candles_map) != len(usdt_candles_map):
            try:
                print(f"🔀 [Crypto_PriceService] Data gap detected between markets. Fetching EURUSDT cross-rates for calculations...")
                fx_res = requests.get(self.kline_url, params={**params, 'symbol': 'EURUSDT'}, timeout=10)
                if fx_res.status_code == 200:
                    for c in fx_res.json():
                        d = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d")
                        raw_eur_usdt_history[d] = float(c[4])
            except Exception as e:
                print(f"⚠️ [Crypto_PriceService] Failed to pull backup forex cross-rates: {e}")

        # --- STEP 4: DATABASE WRITE LOOP ---
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            inserted_count = 0
            gap_logged = False

            for candle_date in sorted(list(all_dates)):
                close_price_eur = eur_candles_map.get(candle_date, 0.0)
                close_price_usdt = usdt_candles_map.get(candle_date, 0.0)
                
                if close_price_eur == 0.0 or close_price_usdt == 0.0:
                    eur_usdt_rate = raw_eur_usdt_history.get(candle_date, 1.08)
                    
                    if close_price_eur == 0.0 and close_price_usdt > 0.0:
                        if not gap_logged:
                            print(f"   ℹ️ [Crypto_PriceService] [{candle_date}] Missing {symbol}EUR market. Deriving EUR from native USDT data...")
                            gap_logged = True
                        close_price_eur = close_price_usdt / eur_usdt_rate if eur_usdt_rate > 0 else close_price_usdt * 0.92
                    
                    elif close_price_usdt == 0.0 and close_price_eur > 0.0:
                        if not gap_logged:
                            print(f"   ℹ️ [Crypto_PriceService] [{candle_date}] Missing {symbol}USDT market. Deriving USDT from native EUR data...")
                            gap_logged = True
                        close_price_usdt = close_price_eur * eur_usdt_rate

                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                    VALUES (?, 'CRYPTO', ?, ?, ?)
                """, (symbol, candle_date, close_price_eur, close_price_usdt))
                inserted_count += 1
                
            conn.commit()
            conn.close()
            print(f"✨ [Crypto_PriceService] Successfully synchronized {inserted_count} clean dual-market rows for {symbol}!")     
        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Bulk seeding error writing to cache for {symbol}: {e}")

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
        """Fetches the historical price of a coin at a specific time."""
        symbol = symbol.upper().strip()
        if symbol == 'EUR': return {'price_eur': 1.0, 'price_usdt': 1.08}
        if symbol in ['USD', 'USDT']: return {'price_eur': 0.92, 'price_usdt': 1.0}
        
        date_key = iso_timestamp[:10]
        target_pair = symbol
        if symbol in ['MATIC', 'POL']:
            target_pair = 'MATIC' if date_key < '2024-09-04' else 'POL'
        elif symbol in ['FTM', 'S']:
            target_pair = 'FTM' if date_key < '2025-01-13' else 'S'

        # 1. 🗄️ Isolated Cache Read
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT price_eur, price_usdt FROM historical_prices 
                WHERE asset = ? AND asset_type = 'CRYPTO' AND date = ?
            """, (symbol, date_key))
            row = cursor.fetchone()
            conn.close()
            if row and row[0] is not None and row[1] is not None:
                return {'price_eur': float(row[0]), 'price_usdt': float(row[1])}
        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Cache read error: {e}")
            
        # 2. 💥 CRITICAL CACHE MISS
        print(f"💥 [Crypto_PriceService] CACHE MISS! Hitting Binance API for {symbol} on {date_key}...")
        
        try:
            clean_ts = iso_timestamp.replace('Z', '+00:00')
            parent_dt = datetime.fromisoformat(clean_ts)
            ms_timestamp = int(parent_dt.timestamp() * 1000)
        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Timestamp parsing failed for {iso_timestamp}: {e}")
            return {'price_eur': 0.0, 'price_usdt': 0.0}

        fetched_price_eur = 0.0
        fetched_price_usdt = 0.0
        
        # 3. 🌐 API Lookup Section (Binance Spot)
        try:
            res_eur = requests.get(f"{self.kline_url}?symbol={target_pair}EUR&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
            if res_eur.status_code == 200 and res_eur.json():
                fetched_price_eur = float(res_eur.json()[0][4])

            res_usdt = requests.get(f"{self.kline_url}?symbol={target_pair}USDT&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
            if res_usdt.status_code == 200 and res_usdt.json():
                fetched_price_usdt = float(res_usdt.json()[0][4])

            if fetched_price_eur > 0.0 or fetched_price_usdt > 0.0:
                if fetched_price_eur == 0.0 or fetched_price_usdt == 0.0:
                    fx_res = requests.get(f"{self.kline_url}?symbol=EURUSDT&interval=1m&startTime={ms_timestamp}&limit=1", timeout=5)
                    eur_usdt_rate = float(fx_res.json()[0][4]) if (fx_res.status_code == 200 and fx_res.json()) else 0.0
                    
                    if eur_usdt_rate == 0.0:
                        try:
                            conn = sqlite3.connect(self.db_path)
                            cursor = conn.cursor()
                            cursor.execute("SELECT price_usdt / price_eur FROM historical_prices WHERE asset = 'BTC' AND date = ? AND price_eur > 0", (date_key,))
                            db_rate = cursor.fetchone()
                            conn.close()
                            eur_usdt_rate = float(db_rate[0]) if db_rate else 1.08
                        except Exception:
                            eur_usdt_rate = 1.08
                    
                    if fetched_price_eur == 0.0:
                        fetched_price_eur = fetched_price_usdt / eur_usdt_rate
                    elif fetched_price_usdt == 0.0:
                        fetched_price_usdt = fetched_price_eur * eur_usdt_rate

                print(f"🌐 Binance API Fetch | {target_pair} | Date: {date_key} | Price EUR: €{fetched_price_eur:.4f} | Price USDT: ${fetched_price_usdt:.4f}")
        except Exception as e:
            print(f"⚠️ [Crypto_PriceService] Binance network call failed for {symbol}: {e}")

        # --- REFACTORED DELEGATION PULL ---
        if fetched_price_eur == 0.0 and fetched_price_usdt == 0.0:
            print(f"🔄 [Crypto_PriceService] Binance data unavailable for {symbol} on {date_key}. Route diversion to CoinGecko fallback engine...")
            cg_res = self._fetch_coingecko_fallback(symbol, date_key)
            if cg_res:
                fetched_price_eur = cg_res['price_eur']
                fetched_price_usdt = cg_res['price_usdt']

        # 5. 💾 Isolated Cache Write back to DB
        if fetched_price_eur > 0.0:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                    VALUES (?, 'CRYPTO', ?, ?, ?)
                """, (symbol, date_key, fetched_price_eur, fetched_price_usdt))
                conn.commit()
                conn.close() 
            except Exception as e:
                print(f"⚠️ [Crypto_PriceService] Failed to write fallback cache to database: {e}")
                
        return {'price_eur': fetched_price_eur, 'price_usdt': fetched_price_usdt}