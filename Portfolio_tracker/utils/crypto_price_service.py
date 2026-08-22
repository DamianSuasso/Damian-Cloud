import os
import csv
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Union, Optional, List

from Portfolio_tracker.utils.db_manager import DatabaseManager
from Portfolio_tracker.utils.financial_utils import (
    get_historical_eur_usdt_rate,
    get_missing_price_dates,
    batch_save_prices
)


class CryptoPriceService:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.base_url = "https://api.binance.com/api/v3/ticker/price"
        self.kline_url = "https://api.binance.com/api/v3/klines"
        self.db = db_manager if db_manager else DatabaseManager()

    def _check_cache_freshness(self, symbol: str, start_year: int) -> Tuple[bool, str]:
        """Internal helper to analyze database content against target configurations."""
        default_start = f"{start_year}-01-01"
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), MAX(date) 
                FROM historical_prices 
                WHERE asset = ? AND asset_type = 'CRYPTO' AND price_eur > 0
            """, (symbol,))
            row = cursor.fetchone()
            cursor.close()
            
            if row and len(row) == 2:
                cached_count = row[0] if row[0] is not None else 0
                max_date_str = row[1]
            else:
                cached_count = 0
                max_date_str = None
                
            sixty_days_ago = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
            
            if cached_count > 100 and max_date_str and max_date_str >= sixty_days_ago:
                print(f"✅ [CryptoPriceService] Cache verified for {symbol} (Up to {max_date_str}). Skipping bulk download.")
                return False, ""
                
            if max_date_str:
                last_dt = datetime.strptime(max_date_str, "%Y-%m-%d")
                next_start_date = (last_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                reason = f"Cache ends on {max_date_str}, resuming forward..."
            else:
                next_start_date = default_start
                reason = f"No local records found, seeding from {default_start}..."
                
            print(f"🔄 [CryptoPriceService] Cache synchronization required for {symbol} ({reason})")
            return True, next_start_date
            
        except Exception as e:
            print(f"⚠️ [CryptoPriceService] Pre-flight cache check calculation exception: {e}")
            return True, default_start

    def _package_price_with_cross_rate(self, price_usdt: float, date_key: str) -> Dict[str, float]:
        """Helper method to isolate the database cross-rate calculation logic."""
        eur_usdt_rate = get_historical_eur_usdt_rate(self.db.conn, date_key, default_rate=1.085)
        return {'price_eur': price_usdt / eur_usdt_rate, 'price_usdt': price_usdt}

    def _fetch_coingecko_fallback(self, symbol: str, date_key: Optional[str] = None) -> Union[Dict[str, float], bool]:
        """
        Unified CoinGecko engine routing:
        1. Bulk Seed Mode (date_key=None): Pulls trailing 365 days.
        2. Pinpoint Mode (date_key="YYYY-MM-DD"): Uses /range endpoint to pull window around event.
        3. Emergency Mode: Fall back to local CSV parsing if API fails.
        """
        def parse_local_csv_fallback(target_date_str: str) -> Optional[float]:
            utils_dir = os.path.dirname(os.path.abspath(__file__))
            portfolio_tracker_dir = os.path.dirname(utils_dir)
            csv_path = os.path.join(portfolio_tracker_dir, "imports", "lmwr-usd-max.csv")
            
            if symbol.upper() != "LMWR" or not os.path.exists(csv_path):
                return None

            print(f"📂 [CryptoPriceService] API limit hit. Activating local CSV look-up for {symbol} on {target_date_str}...")
            try:
                target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
                best_price = None
                smallest_delta = float('inf')
                matched_date = ""

                with open(csv_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        raw_date = row['snapped_at'].split(" ")[0]
                        row_dt = datetime.strptime(raw_date, "%Y-%m-%d")
                        
                        delta = abs((target_dt - row_dt).total_seconds())
                        if delta < smallest_delta:
                            smallest_delta = delta
                            best_price = float(row['price'])
                            matched_date = raw_date

                if best_price is not None and smallest_delta < 130000:
                    print(f"🎯 [CryptoPriceService] Local CSV Match Isolated! Target: {target_date_str} | Row: {matched_date} | Price: ${best_price:.4f}")
                    return best_price
                    
                print(f"❌ [CryptoPriceService] Date {target_date_str} falls outside boundaries of local CSV.")
                return None
            except Exception as csv_err:
                print(f"⚠️ [CryptoPriceService] Failed reading from backup file {csv_path}: {csv_err}")
                return None

        coingecko_api_key = os.getenv("COINGECKO_API_KEY")
        if not coingecko_api_key:
            print("❌ [CryptoPriceService] Aborted: COINGECKO_API_KEY environment variable missing.")
            if date_key:
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)
            return None if date_key else False

        gecko_id_map = {"LMWR": "limewire-token", "GRAM": "gram"}
        gecko_id = gecko_id_map.get(symbol.upper(), symbol.lower())
        
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
                print(f"⚠️ [CryptoPriceService] CoinGecko API returned error status: {res.status_code}.")
                if date_key:
                    csv_price = parse_local_csv_fallback(date_key)
                    if csv_price is not None:
                        return self._package_price_with_cross_rate(csv_price, date_key)
                return {'price_eur': 0.0, 'price_usdt': 0.0} if date_key else False

            prices_array = res.json().get("prices", [])
            
            # --- PINPOINT RUN ---
            if date_key:
                target_ts = datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
                best_match = None
                smallest_delta = float('inf')

                for item in prices_array:
                    item_ts = item[0] / 1000
                    delta = abs(target_ts - item_ts)
                    if delta < smallest_delta:
                        smallest_delta = delta
                        best_match = item

                if best_match and smallest_delta < 130000:
                    price_usdt = float(best_match[1])
                    found_date = datetime.fromtimestamp(best_match[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    print(f"🎯 [CryptoPriceService] Match isolated via API range! Target: {date_key} | Found: {found_date} | Price: ${price_usdt:.4f}")
                    return self._package_price_with_cross_rate(price_usdt, date_key)
                
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)

                print(f"❌ [CryptoPriceService] Failed to locate historical window for {symbol} on {date_key}.")
                return {'price_eur': 0.0, 'price_usdt': 0.0}

            # --- BULK SEED CACHE RUN ---
            else:
                records = []
                for item in prices_array:
                    price_usdt = float(item[1])
                    candle_date = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    eur_rate = get_historical_eur_usdt_rate(self.db.conn, candle_date, default_rate=1.085)
                    price_eur = price_usdt / eur_rate
                    records.append((symbol, 'CRYPTO', candle_date, round(price_eur, 4), round(price_usdt, 4)))
                    
                batch_save_prices(self.db, records)
                print(f"✨ [CryptoPriceService] Successfully supplemented {len(records)} historical rows for {symbol} via CoinGecko!")
                return True

        except Exception as e:
            print(f"⚠️ [CryptoPriceService] Core loop exception: {e}")
            if date_key:
                csv_price = parse_local_csv_fallback(date_key)
                if csv_price is not None:
                    return self._package_price_with_cross_rate(csv_price, date_key)
            return {'price_eur': 0.0, 'price_usdt': 0.0} if date_key else False

    def fetch_and_cache_range(self, symbol: str, start_date: str, end_date: str):
        """Fetches missing crypto prices in bulk between start_date and end_date."""
        symbol = symbol.upper().strip()
        if symbol in ['EUR', 'USD', 'USDT']:
            return

        missing_dates = get_missing_price_dates(self.db, symbol, start_date, end_date, asset_type='CRYPTO')
        if not missing_dates:
            print(f"✅ Crypto cache up-to-date for {symbol} between {start_date} and {end_date}.")
            return

        print(f"🚀 Fetching missing crypto prices for {symbol} ({len(missing_dates)} dates missing)...")
        start_dt = datetime.strptime(missing_dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ms_start_timestamp = int(start_dt.timestamp() * 1000)

        search_symbols = [symbol]
        if symbol in ['MATIC', 'POL']:
            search_symbols = ['MATIC', 'POL']
        elif symbol in ['FTM', 'S']:
            search_symbols = ['FTM', 'S']

        params = {'interval': '1d', 'startTime': ms_start_timestamp, 'limit': 1000}
        eur_candles_map = {}
        usdt_candles_map = {}
        all_dates = set()

        for target_ticker in search_symbols:
            # 🇪🇺 Fetch EUR Chart Data
            try:
                res_eur = requests.get(self.kline_url, params={**params, 'symbol': f"{target_ticker}EUR"}, timeout=10)
                if res_eur.status_code == 200 and res_eur.json():
                    for c in res_eur.json():
                        d = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                        if target_ticker == 'MATIC' and d >= '2024-09-04': continue
                        if target_ticker == 'POL' and d < '2024-09-04': continue
                        if target_ticker == 'FTM' and d >= '2025-01-13': continue
                        if target_ticker == 'S' and d < '2025-01-13': continue
                        
                        eur_candles_map[d] = float(c[4])
                        all_dates.add(d)
            except Exception:
                pass
            
            # 🇺🇸 Fetch USDT Chart Data
            try:
                res_usdt = requests.get(self.kline_url, params={**params, 'symbol': f"{target_ticker}USDT"}, timeout=10)
                if res_usdt.status_code == 200 and res_usdt.json():
                    for c in res_usdt.json():
                        d = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                        if target_ticker == 'MATIC' and d >= '2024-09-04': continue
                        if target_ticker == 'POL' and d < '2024-09-04': continue
                        if target_ticker == 'FTM' and d >= '2025-01-13': continue
                        if target_ticker == 'S' and d < '2025-01-13': continue 

                        usdt_candles_map[d] = float(c[4])
                        all_dates.add(d)
            except Exception:
                pass

        if not all_dates:
            print(f"🔄 Binance missing {symbol}. Diverting to CoinGecko...")
            self._fetch_coingecko_fallback(symbol)
            return

        raw_eur_usdt_history = {}
        if len(eur_candles_map) != len(usdt_candles_map):
            try:
                fx_res = requests.get(self.kline_url, params={**params, 'symbol': 'EURUSDT'}, timeout=10)
                if fx_res.status_code == 200:
                    for c in fx_res.json():
                        d = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                        raw_eur_usdt_history[d] = float(c[4])
            except Exception as e:
                print(f"⚠️ Failed to pull backup forex rates: {e}")

        records_to_insert = []
        for candle_date in sorted(list(all_dates)):
            if candle_date not in missing_dates:
                continue

            close_price_eur = eur_candles_map.get(candle_date, 0.0)
            close_price_usdt = usdt_candles_map.get(candle_date, 0.0)
            
            if close_price_eur == 0.0 or close_price_usdt == 0.0:
                eur_usdt_rate = raw_eur_usdt_history.get(candle_date, 1.085)
                
                if close_price_eur == 0.0 and close_price_usdt > 0.0:
                    close_price_eur = close_price_usdt / eur_usdt_rate
                elif close_price_usdt == 0.0 and close_price_eur > 0.0:
                    close_price_usdt = close_price_eur * eur_usdt_rate

            records_to_insert.append((
                symbol, 
                'CRYPTO', 
                candle_date, 
                round(close_price_eur, 4), 
                round(close_price_usdt, 4)
            ))

        batch_save_prices(self.db, records_to_insert)
        print(f"✨ Synchronized {len(records_to_insert)} dual-market records for {symbol}!")

    def seed_historical_prices_bulk(self, symbol: str, start_year: int = 2023):
        symbol = symbol.upper().strip()
        if symbol in ['EUR', 'USDT']: 
            return
        
        needs_sync, sync_start_str = self._check_cache_freshness(symbol, start_year)
        if not needs_sync:
            return

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.fetch_and_cache_range(symbol, sync_start_str, today_str)

    def get_eur_price(self, symbol: str) -> float:
        """Fetches the current price of a symbol in EUR."""
        symbol = symbol.upper()
        if symbol == 'EUR': return 1.0
        pairs_to_try = [f"{symbol}EUR", f"{symbol}USDT"]
        
        for pair in pairs_to_try:
            try:
                response = requests.get(f"{self.base_url}?symbol={pair}", timeout=5)
                if response.status_code == 200:
                    return float(response.json()['price'])
            except Exception:
                continue
        return 0.0

    def get_historical_prices(self, symbol: str, iso_timestamp: str) -> Dict[str, float]:
        """Fetches the historical price of a coin at a specific date/time."""
        symbol = symbol.upper().strip()
        if symbol == 'EUR': return {'price_eur': 1.0, 'price_usdt': 1.085}
        if symbol in ['USD', 'USDT']: return {'price_eur': 0.92, 'price_usdt': 1.0}
        
        date_key = iso_timestamp[:10]
        target_pair = symbol
        if symbol in ['MATIC', 'POL']:
            target_pair = 'MATIC' if date_key < '2024-09-04' else 'POL'
        elif symbol in ['FTM', 'S']:
            target_pair = 'FTM' if date_key < '2025-01-13' else 'S'

        # 1. Cache Read
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT price_eur, price_usdt FROM historical_prices 
                WHERE asset = ? AND asset_type = 'CRYPTO' AND date = ?
            """, (symbol, date_key))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0] is not None and row[1] is not None:
                return {'price_eur': float(row[0]), 'price_usdt': float(row[1])}
        except Exception as e:
            print(f"⚠️ [CryptoPriceService] Cache read error: {e}")
            
        # 2. Network Fetch Fallback
        print(f"💥 CACHE MISS! Fetching Binance API for {symbol} on {date_key}...")
        
        try:
            clean_ts = iso_timestamp.replace('Z', '+00:00')
            parent_dt = datetime.fromisoformat(clean_ts)
            ms_timestamp = int(parent_dt.timestamp() * 1000)
        except Exception as e:
            print(f"⚠️ Timestamp parsing failed for {iso_timestamp}: {e}")
            return {'price_eur': 0.0, 'price_usdt': 0.0}

        fetched_price_eur = 0.0
        fetched_price_usdt = 0.0
        
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
                        eur_usdt_rate = get_historical_eur_usdt_rate(self.db.conn, date_key, default_rate=1.085)
                    
                    if fetched_price_eur == 0.0:
                        fetched_price_eur = fetched_price_usdt / eur_usdt_rate
                    elif fetched_price_usdt == 0.0:
                        fetched_price_usdt = fetched_price_eur * eur_usdt_rate

        except Exception as e:
            print(f"⚠️ Binance network call failed for {symbol}: {e}")

        # 3. Delegation Fallback
        if fetched_price_eur == 0.0 and fetched_price_usdt == 0.0:
            cg_res = self._fetch_coingecko_fallback(symbol, date_key)
            if isinstance(cg_res, dict):
                fetched_price_eur = cg_res.get('price_eur', 0.0)
                fetched_price_usdt = cg_res.get('price_usdt', 0.0)

        # 4. Cache Write
        if fetched_price_eur > 0.0:
            batch_save_prices(self.db, [(symbol, 'CRYPTO', date_key, round(fetched_price_eur, 4), round(fetched_price_usdt, 4))])

        return {'price_eur': fetched_price_eur, 'price_usdt': fetched_price_usdt}