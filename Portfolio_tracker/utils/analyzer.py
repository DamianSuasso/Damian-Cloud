from datetime import datetime, timedelta
from Portfolio_tracker.utils.db_manager import DatabaseManager
from Portfolio_tracker.utils.crypto_price_service import Crypto_PriceService
from Portfolio_tracker.utils.stock_price_service import StockPriceService  # 🆕 Import the new stock engine
import time

class PortfolioAnalyzer:
    def __init__(self):
        self.db = DatabaseManager()
        self.price_service = Crypto_PriceService()
        self.stock_price_service = StockPriceService()  # 🆕 Instantiate stock service

    # =========================================================================
    # 1. TRADITIONAL EQUITIES SEGREGATED HELPERS
    # =========================================================================
    
    def _get_active_stock_tickers(self) -> list:
        """Dynamically scans both broker history tables for active assets."""
        tickers = []
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("SELECT DISTINCT isin FROM degiro_history WHERE isin IS NOT NULL AND isin != ''")
            tickers.extend([row[0] for row in cursor.fetchall()])

            cursor.execute("SELECT DISTINCT symbol FROM trade_republic_history WHERE symbol IS NOT NULL AND symbol != ''")
            tickers.extend([row[0] for row in cursor.fetchall()])

            return list(set(tickers))
        except Exception as e:
            print(f"⚠️ [Analyzer] Could not scan broker history for active tickers: {e}")
            return []

    def _get_stock_positions_on_date(self, date_str: str) -> dict:
        """
        Dynamically calculates your cumulative stock positions
        from DEGIRO and Trade Republic ledgers up to a specific date.
        """
        positions = {}
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                SELECT isin, aantal, datum FROM degiro_history
                WHERE datum IS NOT NULL AND datum != ''
            """)
            for isin, shares, trade_date in cursor.fetchall():
                if not isin:
                    continue
                if not trade_date:
                    continue

                try:
                    tx_date = datetime.strptime(trade_date, "%d-%m-%Y")
                except ValueError:
                    continue

                if tx_date > datetime.strptime(date_str, "%Y-%m-%d"):
                    continue

                if isin not in positions:
                    positions[isin] = 0.0

                safe_qty = float(shares or 0.0)
                if safe_qty > 0:
                    positions[isin] += safe_qty
                elif safe_qty < 0:
                    positions[isin] += safe_qty

            cursor.execute("""
                SELECT symbol, shares, date FROM trade_republic_history
                WHERE symbol IS NOT NULL AND symbol != '' AND date IS NOT NULL AND date != ''
            """)
            for symbol, shares, trade_date in cursor.fetchall():
                if not symbol:
                    continue

                try:
                    tx_date = datetime.strptime(trade_date, "%Y-%m-%d")
                except ValueError:
                    continue

                if tx_date > datetime.strptime(date_str, "%Y-%m-%d"):
                    continue

                if symbol not in positions:
                    positions[symbol] = 0.0

                safe_qty = float(shares or 0.0)
                positions[symbol] += safe_qty

        except Exception as e:
            print(f"[Analyzer] Could not compute stock positions on {date_str}: {e}")

        return positions

    # =========================================================================
    # 2. CORE PERFORMANCE & METRICS METHODS
    # =========================================================================

    def calculate_cost_basis(self):
        """Processes full transaction history to calculate average buy prices."""
        # Query matching our updated 9-column database schema layout
        query = """
            SELECT type, asset, amount, fiat_value, fiat_currency, fee, fee_currency 
            FROM bitvavo_history 
            ORDER BY timestamp ASC
        """
        cursor = self.db.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        holdings = {}

        for row in rows:
            tx_type, asset, amount, fiat_value, fiat_currency, fee, fee_currency = row
            
            # Skip native cash/base tracking
            if asset in ['EUR', 'USDT', 'USDC'] or not asset:
                continue

            if asset not in holdings:
                holdings[asset] = {'total_qty': 0.0, 'total_spent_eur': 0.0}

            # Typecast safely to prevent calculations running into None values
            try:
                safe_amount = float(amount) if amount is not None else 0.0
                safe_fiat = float(fiat_value) if fiat_value is not None else 0.0
                safe_fee = float(fee) if fee is not None else 0.0
            except (ValueError, TypeError):
                continue

            # Skip broken or incomplete rows
            if safe_amount <= 0:
                continue

            # Convert fiat value to EUR if it was executed in a stablecoin (e.g., USDC, USDT)
            if fiat_currency and fiat_currency != 'EUR' and safe_fiat > 0:
                # If stablecoin matches, convert its value dynamically using your price engine
                stable_to_eur_rate = self.price_service.get_eur_price(fiat_currency)
                if stable_to_eur_rate > 0:
                    safe_fiat = safe_fiat * stable_to_eur_rate

            # Convert fee value to EUR if your fee was deducted in a non-EUR currency
            if fee_currency and fee_currency != 'EUR' and safe_fee > 0:
                fee_to_eur_rate = self.price_service.get_eur_price(fee_currency)
                if fee_to_eur_rate > 0:
                    safe_fee = safe_fee * fee_to_eur_rate

            # If we bought or received staking rewards
            if tx_type in ['buy', 'staking', 'deposit', 'distribution']:
                holdings[asset]['total_qty'] += safe_amount
                if tx_type == 'buy':
                    # Total spent is now directly the clean EUR-equivalent fiat cost + fee
                    holdings[asset]['total_spent_eur'] += safe_fiat + safe_fee

            # If we sold or withdrew
            elif tx_type in ['sell', 'withdrawal']:
                if holdings[asset]['total_qty'] > 0:
                    share_of_portfolio = safe_amount / holdings[asset]['total_qty']
                    holdings[asset]['total_spent_eur'] -= (holdings[asset]['total_spent_eur'] * share_of_portfolio)
                    holdings[asset]['total_qty'] -= safe_amount
                    
                # Guard against floating-point rounding forcing total_qty slightly below 0
                if holdings[asset]['total_qty'] < 0:
                    holdings[asset]['total_qty'] = 0.0
                    holdings[asset]['total_spent_eur'] = 0.0

        # Final pass to compute average break-even metrics
        summary = {}
        for asset, data in holdings.items():
            qty = data['total_qty']
            spent = data['total_spent_eur']
            
            if qty > 0.00001:
                avg_price = spent / qty if spent > 0 else 0.0
                
                if asset == 'BNB' and avg_price == 0.0:
                    avg_price = 251.59 / 1.08
                    spent = qty * avg_price

                summary[asset] = {
                    'current_holdings': round(qty, 6),
                    'total_invested_eur': round(spent, 2),
                    'average_buy_price': round(avg_price, 4)
                }
                
        return summary
    
    def get_portfolio_snapshot_on_date(self, target_date_str):
        """Reconstructs asset balances and portfolio value up to a certain date."""
        # Updated to check history constraints cleanly using new column variables
        query = """
            SELECT type, asset, amount FROM bitvavo_history 
            WHERE date(timestamp) <= date(?) 
            ORDER BY timestamp ASC
        """
        cursor = self.db.conn.cursor()
        cursor.execute(query, (target_date_str,))
        rows = cursor.fetchall()
        
        balances = {}
        for row in rows:
            tx_type, asset, amount = row
            if asset == 'EUR' or not asset: 
                continue
            if asset not in balances: 
                balances[asset] = 0.0
            
            try:
                safe_amount = float(amount) if amount is not None else 0.0
            except (ValueError, TypeError):
                continue

            if tx_type in ['buy', 'staking', 'deposit', 'distribution']:
                balances[asset] += safe_amount
            elif tx_type in ['sell', 'withdrawal']:
                balances[asset] -= safe_amount
        
        # Value those historical balances using historical pricing engines
        report = {}
        total_portfolio_fiat = 0.0
        pseudo_timestamp = f"{target_date_str}T23:59:00.000Z"
        
        for asset, qty in balances.items():
            if qty > 0.00001:
                hist_price = self.price_service.get_historical_prices(asset, pseudo_timestamp)
                # Fallback to current spot value if historical candle lookup fails
                if hist_price == 0.0:
                    hist_price = self.price_service.get_eur_price(asset)
                    
                sub_total = qty * hist_price
                total_portfolio_fiat += sub_total
                report[asset] = {"quantity": round(qty, 6), "value_eur": round(sub_total, 2)}
                
        report["TOTAL_NET_WORTH_EUR"] = round(total_portfolio_fiat, 2)
        return report

    def get_portfolio_historical_timeline(self, start_date_str=None, interval_days=1):
        """Ultra-optimized timeline tracking cash balances dynamically."""
        cursor = self.db.conn.cursor()
        
        # 1. Determine timeline boundaries
        if not start_date_str:
            cursor.execute("SELECT MIN(timestamp) FROM bitvavo_history")
            first_tx = cursor.fetchone()[0]
            if not first_tx:
                return []
            current_date = datetime.strptime(first_tx[:10], "%Y-%m-%d")
        else:
            current_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            
        end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        timeline_data = []

        # 2. Pull all crypto transactions once, including both exchange and cold wallet flows
        all_tx_query = """
            SELECT type AS tx_type, asset, amount, fiat_value, fiat_currency, fee, fee_currency, timestamp
            FROM bitvavo_history
            UNION ALL
            SELECT direction AS tx_type, coin AS asset, amount, 0.0 AS fiat_value, 'EUR' AS fiat_currency, 0.0 AS fee, 'EUR' AS fee_currency, timestamp
            FROM cold_wallet_history
            ORDER BY timestamp ASC
        """
        cursor.execute(all_tx_query)
        all_transactions = cursor.fetchall()
        
        tx_index = 0
        total_tx_count = len(all_transactions)

        # Persistent memory state tracking across time
        running_holdings = {}
        total_days_processed = 0
        stats = {
            "tx_processing_time": 0.0,
            "db_cache_lookup_time": 0.0,
            "network_api_time": 0.0,
            "math_and_compile_time": 0.0
        }
        
        print("\n🚀 [Analyzer] Starting historical timeline processing (Fiat, Crypto & Stocks Unified)...")

        # 3. Step through time sequentially
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            pseudo_timestamp = f"{date_str}T23:59:00.000Z"
            
            print(f"⏳ [Analyzer] Processing Date: {date_str} | Days Analyzed: {total_days_processed}...", end="\r", flush=True)
            
            # 🔄 Update running crypto balances with transactions that happened up to today
            t0 = time.perf_counter()
            while tx_index < total_tx_count:
                tx = all_transactions[tx_index]
                tx_type, asset, amount, fiat_value, fiat_currency, fee, fee_currency, timestamp = tx
                
                if datetime.strptime(timestamp[:10], "%Y-%m-%d") > current_date:
                    break
                    
                tx_index += 1
                if not asset: 
                    continue
                    
                if asset not in running_holdings:
                    running_holdings[asset] = {'qty': 0.0, 'invested': 0.0}
                    
                qty = float(amount or 0)
                fiat = float(fiat_value or 0)
                safe_fee = float(fee or 0)
                tx_type_clean = tx_type.lower()
                
                if tx_type_clean in ['buy', 'staking', 'deposit', 'distribution', 'inbound']:
                    running_holdings[asset]['qty'] += qty
                    if tx_type_clean == 'buy':
                        running_holdings[asset]['invested'] += fiat
                elif tx_type_clean in ['sell', 'withdrawal', 'outbound']:
                    if running_holdings[asset]['qty'] > 0:
                        share = qty / running_holdings[asset]['qty']
                        if tx_type_clean == 'sell':
                            running_holdings[asset]['invested'] -= (running_holdings[asset]['invested'] * share)
                        running_holdings[asset]['qty'] -= qty
                
                if tx_type_clean == 'buy':
                    pay_currency = fiat_currency if fiat_currency else 'EUR'
                    if pay_currency not in running_holdings:
                        running_holdings[pay_currency] = {'qty': 0.0, 'invested': 0.0}
                    running_holdings[pay_currency]['qty'] -= fiat

                    f_curr = fee_currency if fee_currency else 'EUR'
                    if f_curr not in running_holdings:
                        running_holdings[f_curr] = {'qty': 0.0, 'invested': 0.0}
                    running_holdings[f_curr]['qty'] -= safe_fee

                elif tx_type_clean == 'sell':
                    rec_currency = fiat_currency if fiat_currency else 'EUR'
                    if rec_currency not in running_holdings:
                        running_holdings[rec_currency] = {'qty': 0.0, 'invested': 0.0}
                    running_holdings[rec_currency]['qty'] += fiat

                    f_curr = fee_currency if fee_currency else 'EUR'
                    if f_curr not in running_holdings:
                        running_holdings[f_curr] = {'qty': 0.0, 'invested': 0.0}
                    running_holdings[f_curr]['qty'] -= safe_fee

            stats["tx_processing_time"] += (time.perf_counter() - t0)

            # 4. Calculate Values & Profit per share directly from memory state
            assets_metrics = {}
            total_value_eur = 0.0
            total_invested_eur = 0.0
            
            t_math_start = time.perf_counter()

            # Dynamic extraction of the timeline day's FX rate to value USD-pegged stablecoins
            try:
                cursor.execute(
                    "SELECT price_usdt / price_eur FROM historical_prices WHERE asset = 'BTC' AND date = ? AND price_eur > 0", 
                    (date_str,)
                )
                db_rate = cursor.fetchone()
                current_fx_rate = float(db_rate[0]) if db_rate else 1.08
            except Exception:
                current_fx_rate = 1.08

            # --- A. COMPILE CRYPTO METRICS ---
            for asset, data in running_holdings.items():
                current_qty = data['qty']
                total_spent = data['invested']
                
                # --- BNB COST BASIS INTERCEPTION ---
                if asset == 'BNB' and current_qty > 0.0001 and total_spent == 0.0:
                    calculated_price_eur = 251.59 / current_fx_rate
                    total_spent = current_qty * calculated_price_eur
                
                if current_qty > 0.0001:
                    if asset == 'EUR':
                        historical_price = 1.0
                        historical_price_usdt = current_fx_rate
                        avg_buy_price = 1.0
                        profit_per_share = 0.0
                        total_profit_asset = 0.0
                    elif asset in ['USDT', 'USDC']:
                        historical_price = 1.0 / current_fx_rate
                        historical_price_usdt = 1.0
                        avg_buy_price = 1.0
                        profit_per_share = 0.0
                        total_profit_asset = 0.0
                    else:
                        # Volatile Cryptocurrencies (Original Core Engine Logic)
                        t_price_start = time.perf_counter()
                        prices = self.price_service.get_historical_prices(asset, pseudo_timestamp)
                        historical_price = prices.get('price_eur', 0.0)
                        historical_price_usdt = prices.get('price_usdt', 0.0)
                        t_price_delta = time.perf_counter() - t_price_start

                        if t_price_delta > 0.05:
                            stats["network_api_time"] += t_price_delta
                        else:
                            stats["db_cache_lookup_time"] += t_price_delta

                        avg_buy_price = total_spent / current_qty if total_spent > 0 else 0.0
                        profit_per_share = historical_price - avg_buy_price
                        total_profit_asset = (current_qty * historical_price) - total_spent

                    asset_market_val = current_qty * historical_price
                    total_value_eur += asset_market_val
                    
                    # Only add traditional assets to 'invested' to keep ROI calculations meaningful
                    if asset not in ['EUR', 'USDT', 'USDC']:
                        total_invested_eur += total_spent
                    
                    assets_metrics[asset] = {
                        "asset_type": "CRYPTO",
                        "balance": round(current_qty, 4),
                        "value_eur": round(asset_market_val, 2),
                        "avg_buy_price": round(avg_buy_price, 4),
                        "historical_price": round(historical_price, 4),
                        "profit_per_share": round(profit_per_share, 4),
                        "total_profit_eur": round(total_profit_asset, 2),
                        "historical_price_usdt": round(historical_price_usdt, 4)
                    }

            # --- B. COMPILE STOCKS METRICS ---
            stock_positions = self._get_stock_positions_on_date(date_str)
            for ticker, stock_qty in stock_positions.items():
                if stock_qty > 0.001:
                    resolved_ticker = ticker
                    if ticker and ticker.upper() in {'EUR', 'USD', 'USDT', 'USDC'}:
                        continue

                    try:
                        stk_price_eur = self.stock_price_service.get_price_on_date(resolved_ticker, date_str, preferred_currency="EUR")
                        stk_price_usd = self.stock_price_service.get_price_on_date(resolved_ticker, date_str, preferred_currency="USDT")
                    except Exception:
                        stk_price_eur = 0.0
                        stk_price_usd = 0.0

                    cursor.execute("SELECT sector FROM asset_ticker_map WHERE resolved_ticker = ? LIMIT 1", (resolved_ticker,))
                    sector_row = cursor.fetchone()
                    stock_sector = sector_row[0] if sector_row else "Unknown"

                    stk_market_val = stock_qty * stk_price_eur if stk_price_eur else 0.0
                    total_value_eur += stk_market_val

                    total_stock_spent = 0.0
                    total_invested_eur += total_stock_spent

                    assets_metrics[resolved_ticker] = {
                        "asset_type": "STOCK",
                        "balance": round(stock_qty, 4),
                        "value_eur": round(stk_market_val, 2),
                        "avg_buy_price": 0.0,
                        "historical_price": round(stk_price_eur, 4),
                        "profit_per_share": 0.0,
                        "total_profit_eur": 0.0,
                        "historical_price_usdt": round(stk_price_usd, 4),
                        "sector": stock_sector
                    }

            stats["math_and_compile_time"] += (time.perf_counter() - t_math_start)   
                
            total_unrealized_profit = total_value_eur - total_invested_eur
            roi_percentage = (total_unrealized_profit / total_invested_eur * 100) if total_invested_eur > 0 else 0.0
            
            timeline_data.append({
                "date": date_str,
                "total_portfolio_value_eur": round(total_value_eur, 2),
                "total_invested_eur": round(total_invested_eur, 2),
                "total_unrealized_profit_eur": round(total_unrealized_profit, 2),
                "roi_percentage": round(roi_percentage, 2),
                "assets": assets_metrics
            })
            
            total_days_processed += 1
            current_date += timedelta(days=interval_days)
            
            if total_days_processed % 20 == 0:
                print(f"\n⏱️ --- Performance Metrics at Day {total_days_processed} ({date_str}) ---")
                print(f" 📦 Tx Log Progression:  {stats['tx_processing_time']:.4f}s")
                print(f" 🗄️ SQLite Cache Hits:    {stats['db_cache_lookup_time']:.4f}s")
                print(f" 🌐 Binance Network Hits: {stats['network_api_time']:.4f}s")
                print(f" 🧮 Pure Memory Math:     {stats['math_and_compile_time']:.4f}s")
                print("-" * 50)
                
        print(f"\n✅ [Analyzer] Timeline processing complete! Total milestones calculated: {len(timeline_data)}\n")
        return timeline_data
    
    def warm_up_price_cache(self, start_year=2023):
        """Pre-seeds historical values for all unique assets found in the DB."""
        print("\n📋 [Analyzer] Scanning database for active assets...")
        target_assets = []
        start_date = f"{start_year}-01-01"
        
        try:
            cursor = self.db.conn.cursor()
            # Extract existing tables to prevent crashing on uninitialized environments
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            # Scan Bitvavo ledger
            if 'bitvavo_history' in existing_tables:
                cursor.execute("""
                    SELECT DISTINCT asset FROM bitvavo_history 
                    WHERE asset IS NOT NULL AND asset NOT IN ('EUR', 'USDT', 'USDC', '')
                """)
                target_assets.extend([row[0] for row in cursor.fetchall()])
                
            # Scan Cold Wallet ledger
            if 'cold_wallet_history' in existing_tables:
                cursor.execute("""
                    SELECT DISTINCT coin AS asset FROM cold_wallet_history 
                    WHERE coin IS NOT NULL AND coin NOT IN ('EUR', 'USDT', 'USDC', '')
                """)
                target_assets.extend([row[0] for row in cursor.fetchall()])
                
            # De-duplicate the asset list
            target_assets = list(set(target_assets))
            print(f"🎯 [Analyzer] Total unique volatile crypto assets discovered: {', '.join(target_assets) if target_assets else 'None'}")
            
            # --- 🆕 traditional stock pre-seed layer ---
            print("⚡ [Analyzer] Warming up local stock price storage cache via bulk channels...")
            target_stocks = self._get_active_stock_tickers()
            for stock_ticker in target_stocks:
                if stock_ticker and stock_ticker.upper() not in {'EUR', 'USD', 'USDT', 'USDC'}:
                    # This downloads the full 3+ year history block to SQLite in ONE request
                    self.stock_price_service.fetch_and_cache_historical_prices(stock_ticker, start_date=start_date)
        
            print("✨ [Analyzer] Stock price cache warming sequence fully completed!\n")

        except Exception as e:
            print(f"⚠️ [Analyzer] Failed to scan asset tables automatically: {e}")
            # Safe historical fallback list
            target_assets = ['BTC', 'ETH', 'ADA', 'BNB', 'SOL', 'LINK', 'XRP']

        # Bulk pre-seed historical pricing blocks
        if target_assets:
            print("⚡ [Analyzer] Warming up local crypto price storage cache via bulk channels...")
            for asset in target_assets:
                try:
                    # Uses your existing bulk seeding infrastructure to fill local db caches
                    self.price_service.seed_historical_prices_bulk(asset, start_year=start_year)
                except Exception as e:
                    print(f"⚠️ [Analyzer] Could not pre-seed bulk data for {asset}: {e}")
            print("✅ [Analyzer] Price cache optimization layer warm and ready.")