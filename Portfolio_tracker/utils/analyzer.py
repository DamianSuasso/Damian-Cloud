from datetime import datetime, timedelta
from utils.db_manager import DatabaseManager
from utils.price_service import PriceService
import time

class PortfolioAnalyzer:
    def __init__(self):
        self.db = DatabaseManager()
        self.price_service = PriceService()

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
            if asset == 'EUR' or not asset:
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
            
            if qty > 0.00001:  # Filter out dust balances
                avg_price = spent / qty if spent > 0 else 0.0
                summary[asset] = {
                    'current_holdings': round(qty, 6),
                    'total_invested_eur': round(spent, 2),
                    'average_buy_price': round(avg_price, 4) # 4 decimals handles low-priced assets beautifully
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
        """
        Ultra-optimized single-pass timeline calculation.
        Bypasses get_portfolio_snapshot_on_date to eliminate nested loop bottlenecks.
        """
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
            
        end_date = datetime.utcnow()
        timeline_data = []

        # 2. Pull all transactions once
        all_tx_query = """
            SELECT type AS tx_type, asset, amount, fiat_value, timestamp
            FROM bitvavo_history 
            UNION ALL
            SELECT direction AS tx_type, coin AS asset, amount, 0.0 AS fiat_value, timestamp
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
        # Persistent performance counters
        stats = {
            "tx_processing_time": 0.0,
            "db_cache_lookup_time": 0.0,
            "network_api_time": 0.0,
            "math_and_compile_time": 0.0
        }
        
        print("\n🚀 Starting ultra-optimized historical timeline calculation...")

        # 3. Step through time sequentially
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            pseudo_timestamp = f"{date_str}T23:59:00.000Z"
            
            print(f"⏳ Processing Date: {date_str} | Days Analyzed: {total_days_processed}...", end="\r", flush=True)
            
            # 🔄 Update running balances with transactions that happened up to today
            t0 = time.perf_counter()
            while tx_index < total_tx_count:
                tx = all_transactions[tx_index]
                tx_type, asset, amount, fiat_value, timestamp = tx
                
                if datetime.strptime(timestamp[:10], "%Y-%m-%d") > current_date:
                    break
                    
                tx_index += 1
                
                if asset == 'EUR' or not asset: 
                    continue
                    
                if asset not in running_holdings:
                    running_holdings[asset] = {'qty': 0.0, 'invested': 0.0}
                    
                qty = float(amount or 0)
                fiat = float(fiat_value or 0)
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
            stats["tx_processing_time"] += (time.perf_counter() - t0)

            # 4. Calculate Values & Profit per share directly from memory state
            assets_metrics = {}
            total_value_eur = 0.0
            total_invested_eur = 0.0
            
            for asset, data in running_holdings.items():
                current_qty = data['qty']
                total_spent = data['invested']
                
                if current_qty > 0.0001:
                    t_price_start = time.perf_counter()
                    # Fetch price directly using your persistent caching engine
                    prices = self.price_service.get_historical_prices(asset, pseudo_timestamp)
                    historical_price = prices.get('price_eur', 0.0)
                    t_price_delta = time.perf_counter() - t_price_start

                    if t_price_delta > 0.05:
                        stats["network_api_time"] += t_price_delta
                    else:
                        stats["db_cache_lookup_time"] += t_price_delta

                    t_math_start = time.perf_counter()
                    asset_market_val = current_qty * historical_price
                    avg_buy_price = total_spent / current_qty if total_spent > 0 else 0.0
                    profit_per_share = historical_price - avg_buy_price
                    total_profit_asset = asset_market_val - total_spent
                    
                    total_value_eur += asset_market_val
                    total_invested_eur += total_spent
                    
                    assets_metrics[asset] = {
                        "balance": round(current_qty, 4),
                        "value_eur": round(asset_market_val, 2),
                        "avg_buy_price": round(avg_buy_price, 4),
                        "historical_price": round(historical_price, 4),
                        "profit_per_share": round(profit_per_share, 4),
                        "total_profit_eur": round(total_profit_asset, 2),
                        "historical_price_usdt": round(prices.get('price_usdt', 0.0), 4)
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
                
        print(f"\n✅ Timeline processing complete! Total milestones calculated: {len(timeline_data)}\n")
        return timeline_data