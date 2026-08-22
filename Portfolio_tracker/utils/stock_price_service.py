import os
import math
import requests
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple, Optional
import yfinance as yf

from Portfolio_tracker.utils.db_manager import DatabaseManager
from Portfolio_tracker.utils.financial_utils import get_historical_eur_usdt_rate, get_missing_price_dates


class StockPriceService:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager if db_manager else DatabaseManager()
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def _parse_date(self, value) -> date:
        if value is None:
            raise ValueError("Date value cannot be None")
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date()
        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                raise ValueError("Date string is empty")
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(raw_value, fmt).date()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date()
            except ValueError as exc:
                raise ValueError(f"Unsupported date format: {value}") from exc
        raise TypeError(f"Unsupported date type: {type(value).__name__}")

    def _resolve_market_ticker(self, ticker: str) -> str:
        if not ticker:
            return ""
        normalized = str(ticker).strip().upper()
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT resolved_ticker FROM asset_ticker_map WHERE identifier = ? LIMIT 1", (normalized,))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                return str(row[0]).strip().upper()
        except Exception as e:
            print(f"⚠️ [StockPriceService] Local ticker map lookup error inside service: {e}")
        return normalized

    def _save_batch_stock_prices(self, price_records: List[Tuple[str, str, float, float]]):
        """
        Custom batch insert specifically matching the historical_prices table schema:
        price_records: [(resolved_ticker, date_str, price_eur, price_usdt), ...]
        """
        if not price_records:
            return

        query = """
        INSERT INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
        VALUES (?, 'STOCK', ?, ?, ?)
        ON CONFLICT(asset, asset_type, date) DO UPDATE SET 
            price_eur=excluded.price_eur,
            price_usdt=excluded.price_usdt
        """
        try:
            cursor = self.db.conn.cursor()
            cursor.executemany(query, price_records)
            self.db.conn.commit()
            cursor.close()
        except Exception as e:
            print(f"⚠️ [StockPriceService] Error batch saving stock prices to DB: {e}")

    def fetch_and_cache_range(self, ticker: str, start_date: str, end_date: str):
        """Fetches missing stock prices in bulk using yfinance and caches them with currency conversion."""
        resolved_ticker = self._resolve_market_ticker(ticker)
        if not resolved_ticker:
            return

        missing_dates = get_missing_price_dates(self.db, resolved_ticker, start_date, end_date)
        if not missing_dates:
            print(f"✅ [StockPriceService] Cache up-to-date for {resolved_ticker} between {start_date} and {end_date}.")
            return

        fetch_start = missing_dates[0]
        fetch_end = (datetime.strptime(missing_dates[-1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"📈 [StockPriceService] Bulk downloading stock prices for {resolved_ticker} from {fetch_start} to {fetch_end}...")
        try:
            ticker_obj = yf.Ticker(resolved_ticker)
            raw_currency = ticker_obj.fast_info.get('currency', 'USD').upper()
            
            df = yf.download(resolved_ticker, start=fetch_start, end=fetch_end, progress=False)
            if df.empty:
                return

            records_to_insert = []
            if hasattr(df.columns, 'levels'):
                close_prices = df['Close'][resolved_ticker] if resolved_ticker in df['Close'] else df['Close'].iloc[:, 0]
            else:
                close_prices = df['Close']

            for date_idx, price in close_prices.items():
                date_str = date_idx.strftime("%Y-%m-%d")
                
                # Check for valid numerical price and date match
                if price is not None and not math.isnan(price) and date_str in missing_dates:
                    base_price = float(price)
                    eur_usdt_rate = get_historical_eur_usdt_rate(self.db.conn, date_str, default_rate=1.085)
                    
                    if raw_currency == "EUR":
                        price_eur = base_price
                        price_usdt = base_price * eur_usdt_rate
                    elif raw_currency in ("USD", "USDT"):
                        price_eur = base_price / eur_usdt_rate
                        price_usdt = base_price
                    elif raw_currency in ("GBP", "GBP"):
                        actual_gbp = base_price / 100.0 if raw_currency == "GBP" else base_price
                        price_eur = actual_gbp * 1.182
                        price_usdt = price_eur * eur_usdt_rate
                    else:
                        price_eur = base_price
                        price_usdt = base_price * eur_usdt_rate

                    records_to_insert.append((
                        resolved_ticker, 
                        date_str, 
                        round(price_eur, 4), 
                        round(price_usdt, 4)
                    ))

            self._save_batch_stock_prices(records_to_insert)
            print(f"💾 [StockPriceService] Caching complete for {resolved_ticker}. Saved {len(records_to_insert)} records.")

        except Exception as e:
            print(f"❌ [StockPriceService] Error fetching bulk stock prices for {resolved_ticker}: {e}")

    def fetch_and_cache_historical_prices(self, ticker: str, start_date: str = "2020-01-01"):
        """Fallback direct Yahoo REST API route for single/individual asset synchronization."""
        resolved_ticker = self._resolve_market_ticker(ticker)
        if not resolved_ticker:
            return

        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT MAX(date) FROM historical_prices 
                WHERE asset = ? AND asset_type = 'STOCK'
            """, (resolved_ticker,))
            max_date_row = cursor.fetchone()
            cursor.close()

            if max_date_row and max_date_row[0]:
                max_date_str = max_date_row[0]
                max_date_obj = datetime.strptime(max_date_str, "%Y-%m-%d").date()
                today_obj = datetime.now(timezone.utc).date()

                # Cache is valid — return silently without printing
                if (today_obj - max_date_obj).days <= 3:
                    return
        except Exception as e:
            print(f"⚠️ [StockPriceService] Error checking local cache freshness for {resolved_ticker}: {e}")

        try:
            start_dt = self._parse_date(start_date)
            start_dt = datetime.combine(start_dt, datetime.min.time(), tzinfo=timezone.utc)
            start_ts = int((start_dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
            end_ts = int((datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
        except Exception as exc:
            print(f"❌ [StockPriceService] Invalid date format '{start_date}': {exc}")
            return

        print(f"📈 [StockPriceService] REST Network Syncing: {resolved_ticker}...")
        urls = [
            f"https://query1.finance.yahoo.com/v8/finance/chart/{resolved_ticker}?period1={start_ts}&period2={end_ts}&interval=1d",
            f"https://query2.finance.yahoo.com/v8/finance/chart/{resolved_ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
        ]
        data = None

        for url in urls:
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    break
            except Exception:
                continue

        cursor = self.db.conn.cursor()

        if not data or "chart" not in data or not data["chart"].get("result") or data["chart"]["result"][0] is None:
            print(f"⚠️ [StockPriceService] Failed payload trace for {resolved_ticker}. Writing safety boundary marker.")
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                VALUES (?, 'STOCK', ?, -1.0, -1.0)
            """, (resolved_ticker, today_str))
            self.db.conn.commit()
            cursor.close()
            return

        result = data["chart"]["result"][0]
        meta = result.get("meta", {})
        raw_currency = meta.get("currency", "USD")
        timestamps = result.get("timestamp", [])
        indicators = result.get("indicators", {}).get("quote", [{}])[0]
        close_prices = indicators.get("close", [])

        if not timestamps or not close_prices:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                VALUES (?, 'STOCK', ?, -1.0, -1.0)
            """, (resolved_ticker, today_str))
            self.db.conn.commit()
            cursor.close()
            return

        inserted_count = 0
        for ts, price in zip(timestamps, close_prices):
            if price is None:
                continue
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            base_price = float(price)
            eur_usdt_rate = get_historical_eur_usdt_rate(self.db.conn, date_str, default_rate=1.085)
            
            if raw_currency == "EUR":
                price_eur = base_price
                price_usdt = base_price * eur_usdt_rate
            elif raw_currency in ("USD", "USDT"):
                price_eur = base_price / eur_usdt_rate
                price_usdt = base_price
            elif raw_currency in ("GBP", "GBp"):
                actual_gbp = base_price / 100.0 if raw_currency == "GBp" else base_price
                price_eur = actual_gbp * 1.182
                price_usdt = price_eur * eur_usdt_rate
            else:
                price_eur = base_price
                price_usdt = base_price * eur_usdt_rate

            cursor.execute("""
                INSERT OR REPLACE INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
                VALUES (?, 'STOCK', ?, ?, ?)
            """, (resolved_ticker, date_str, round(price_eur, 4), round(price_usdt, 4)))
            inserted_count += 1

        self.db.conn.commit()
        cursor.close()
        print(f"💾 [StockPriceService] Caching complete for {resolved_ticker}. Processed {inserted_count} market days.")

    def get_price_on_date(self, ticker: str, target_date: str, preferred_currency: str = "EUR") -> float:
        column_target = "price_eur" if preferred_currency.upper() == "EUR" else "price_usdt"
        resolved_ticker = self._resolve_market_ticker(ticker)
        if not resolved_ticker:
            return 0.0

        def _execute_lookback_loop() -> float:
            cursor = self.db.conn.cursor()
            current_lookup = self._parse_date(target_date)
            
            for _ in range(10):
                date_str = current_lookup.strftime("%Y-%m-%d")
                cursor.execute(f"""
                    SELECT {column_target} FROM historical_prices 
                    WHERE asset = ? AND asset_type = 'STOCK' AND date = ?
                """, (resolved_ticker, date_str))
                row = cursor.fetchone()
                
                if row and row[0] is not None:
                    val = float(row[0])
                    cursor.close()
                    return max(0.0, val) if val != -1.0 else 0.0
                
                current_lookup -= timedelta(days=1)
                
            cursor.close()
            return 0.0

        price = _execute_lookback_loop()
        
        if price == 0.0:
            self.fetch_and_cache_historical_prices(resolved_ticker)
            price = _execute_lookback_loop()

        return price