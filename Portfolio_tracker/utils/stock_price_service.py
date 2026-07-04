import os
import re
import requests
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from Portfolio_tracker.utils.db_manager import DatabaseManager

class StockPriceService:
    def __init__(self):
        self.db = DatabaseManager()
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
            print(f"⚠️ Local ticker map lookup error inside service: {e}")
        return normalized

    def _build_yahoo_chart_urls(self, ticker: str, start_ts: int, end_ts: int) -> list[str]:
        # Clean the raw literal ticker string out out to remove character encoding drops
        cleaned_ticker = ticker.strip().upper()
        return [
            f"https://query1.finance.yahoo.com/v8/finance/chart/{cleaned_ticker}?period1={start_ts}&period2={end_ts}&interval=1d",
            f"https://query2.finance.yahoo.com/v8/finance/chart/{cleaned_ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
        ]

    def _get_historical_eur_usdt_rate(self, date_str: str) -> float:
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT price_usdt / price_eur FROM historical_prices 
                WHERE asset = 'BTC' AND asset_type = 'CRYPTO' AND date = ? AND price_eur > 0
            """, (date_str,))
            row = cursor.fetchone()
            cursor.close()
            return float(row[0]) if row and row[0] is not None else 1.085
        except Exception:
            return 1.085

    def fetch_and_cache_historical_prices(self, ticker: str, start_date: str = "2020-01-01"):
        """Queries Yahoo Finance API. Drops dead markers if assets are unreachable to prevent infinite looping."""
        resolved_ticker = self._resolve_market_ticker(ticker)
        
        if not resolved_ticker:
            return

        # 🔍 NEW: Check if data or a recent failure marker already exists
        try:
            cursor = self.db.conn.cursor()
            # Look for the absolute most recent record we have for this stock
            cursor.execute("""
                SELECT MAX(date) FROM historical_prices 
                WHERE asset = ? AND asset_type = 'STOCK'
            """, (resolved_ticker,))
            max_date_row = cursor.fetchone()
            cursor.close()

            if max_date_row and max_date_row[0]:
                max_date_str = max_date_row[0]
                max_date_obj = datetime.strptime(max_date_str, "%Y-%m-%d").date()
                today_obj = datetime.utcnow().date()

                # If our newest record is within the last 3 days, consider it fresh.
                # This safely accounts for weekend market closures.
                if (today_obj - max_date_obj).days <= 3:
                    print(f"✅ [Stock Price Service] Cache verified for {resolved_ticker} (Last updated: {max_date_str}). Skipping sync.")
                    return
        except Exception as e:
            print(f"⚠️ Error checking local cache freshness for {resolved_ticker}: {e}")

        try:
            start_dt = self._parse_date(start_date)
            start_dt = datetime.combine(start_dt, datetime.min.time(), tzinfo=timezone.utc)
            start_ts = int((start_dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
            end_ts = int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds())
        except Exception as exc:
            print(f"❌ Invalid date format '{start_date}': {exc}")
            return

        print(f"📈 [Stock Price Service] Network Syncing: {resolved_ticker}...")
        urls = self._build_yahoo_chart_urls(resolved_ticker, start_ts, end_ts)
        response, data = None, None

        for url in urls:
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    break
            except Exception:
                continue

        cursor = self.db.conn.cursor()

        # If API failed or payload structural elements are missing, write a failure marker
        if not data or "chart" not in data or not data["chart"].get("result") or data["chart"]["result"][0] is None:
            print(f"⚠️ Failed payload trace for {resolved_ticker}. Writing safety boundary marker.")
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
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
            # Write a marker record if data exists but rows are blank
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
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
            date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            base_price = float(price)
            eur_usdt_rate = self._get_historical_eur_usdt_rate(date_str)
            
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
        print(f"💾 Caching complete for {resolved_ticker}. Processed {inserted_count} market days.")

    def get_price_on_date(self, ticker: str, target_date: str, preferred_currency: str = "EUR") -> float:
        column_target = "price_eur" if preferred_currency.upper() == "EUR" else "price_usdt"
        resolved_ticker = self._resolve_market_ticker(ticker)
        if not resolved_ticker:
            return 0.0

        def _execute_lookback_loop() -> float:
            cursor = self.db.conn.cursor()
            current_lookup = self._parse_date(target_date)
            
            # Look back up to 10 days to confidently clear wide holiday spans (e.g. Christmas/New Years)
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
                    # Return 0.0 if it hits an API error marker to skip processing errors quietly
                    return max(0.0, val) if val != -1.0 else 0.0
                
                current_lookup -= timedelta(days=1)
                
            cursor.close()
            return 0.0

        # Attempt 1: Fetch straight from SQLite
        price = _execute_lookback_loop()
        return price