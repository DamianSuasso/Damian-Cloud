from utils.db_manager import DatabaseManager
from utils.price_service import PriceService

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
                hist_price = self.price_service.get_historical_eur_price(asset, pseudo_timestamp)
                # Fallback to current spot value if historical candle lookup fails
                if hist_price == 0.0:
                    hist_price = self.price_service.get_eur_price(asset)
                    
                sub_total = qty * hist_price
                total_portfolio_fiat += sub_total
                report[asset] = {"quantity": round(qty, 6), "value_eur": round(sub_total, 2)}
                
        report["TOTAL_NET_WORTH_EUR"] = round(total_portfolio_fiat, 2)
        return report