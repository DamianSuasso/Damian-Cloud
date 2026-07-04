#!/usr/bin/env python3
import sys
import os
from datetime import datetime, timezone

# Dynamically inject the parent project folder into the system path
current_dir = os.path.dirname(os.path.abspath(__file__))  # Points to Portfolio_tracker
parent_dir = os.path.dirname(current_dir)                 # Points to Damian-Cloud
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from Portfolio_tracker.connectors.bitvavo import BitvavoConnector
from Portfolio_tracker.utils.crypto_price_service import Crypto_PriceService
from Portfolio_tracker.utils.analyzer import PortfolioAnalyzer
from Portfolio_tracker.utils.stock_price_service import StockPriceService
from Portfolio_tracker.agents.analyst import SentinelAnalyst

from Portfolio_tracker.sync_crypto import sync_bitvavo
from Portfolio_tracker.sync_cold_wallets import sync_all_wallets
from Portfolio_tracker.sync_stocks import sync_stocks

def main():
    print("=========================================")
    print("         SENTINEL PORTFOLIO CONSOLE       ")
    print("=========================================")

    print("\n[ Initiating Ledger Synchronization Matrix... ]")
    
    # 1. Automatic Auto-Sync on Launch
    try:
        sync_bitvavo()
    except Exception as e:
        print(f"⚠️ [Main] Automatic historical ledger update skipped: {e}")

    cold_balances = {}
    try:
        cold_balances = sync_all_wallets() or {}
    except Exception as e:
        print(f"⚠️ [Main] Automatic cold wallet synchronization skipped: {e}")

    stock_balances = {}
    try:
        stock_balances = sync_stocks() or {} 
    except Exception as e:
        print(f"⚠️ [Main]    Automatic equity broker synchronization skipped: {e}")
                
    # 2. Fetch Live Snapshot Balances & Initialize Engines
    print("\n[ Fetching Current Balances... ]")
    bitvavo = BitvavoConnector()
    bv_balances = bitvavo.get_balance()
    
    price_engine = Crypto_PriceService()
    stock_price_engine = StockPriceService()
    analyzer = PortfolioAnalyzer()
    
    try:
        analyzer.warm_up_price_cache(start_year=2023)
    except Exception as e:
        print(f"⚠️ [Main] Cache warming pipeline skipped: {e}")

    print("[ Compiling Portfolio Historical Timeline... ]")
    try:
        historical_timeline = analyzer.get_portfolio_historical_timeline()
        print(f"✅ [Main] Success: Processed {len(historical_timeline)} historical timeline data points.")
    except Exception as e:
        historical_timeline = []
        print(f"⚠️ [Main] Failed to compile historical data: {e}")

    # 3. Unified Portfolio Snapshot Terminal Display
    print("\n[ Unified Portfolio Snapshot ]")
    print(f"{'SOURCE':<10} | {'ASSET':<12} | {'QTY':<12} | {'VALUE EUR':<10}")
    print("-" * 55)
    
    # Track performance allocations live
    live_crypto_value = 0.0
    live_stock_value = 0.0

    # --- Process Exchange (Bitvavo) ---
    if isinstance(bv_balances, list):
        for asset in bv_balances:
            available_qty = float(asset.get('available', 0) or 0)
            staked_qty = float(asset.get('inOrder', 0) or 0)
            total_qty = available_qty + staked_qty
            
            if total_qty > 0.0001: 
                symbol = asset['symbol'].upper()
                if symbol == 'EUR':
                    continue
                    
                price = price_engine.get_eur_price(symbol)
                asset_val = total_qty * price
                live_crypto_value += asset_val
                print(f"EXCHANGE   | {symbol:<12} | {total_qty:<12.4f} | €{asset_val:,.2f}")
    
    # --- Process Cold Wallets ---
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)):
            price = price_engine.get_eur_price(coin)
            eur_val = status * price
            live_crypto_value += eur_val
            print(f"COLD       | {coin:<12} | {status:<12.4f} | €{eur_val:,.2f}")
        else:
            print(f"COLD       | ❌ {coin:<12} | {status}")

    # --- Process Traditional Stocks & Brokerages ---
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ticker, details in stock_balances.items():
        if isinstance(details, dict) and 'shares' in details:
            qty = float(details['shares'])
            if qty > 0.0001:
                price = stock_price_engine.get_price_on_date(ticker, today_str, preferred_currency="EUR")
                eur_val = qty * price
                live_stock_value += eur_val
                print(f"BROKERAGE  | {ticker:<12} | {qty:<12.4f} | €{eur_val:,.2f}")
            elif qty < -0.0001:
                print(f"BROKERAGE  | ⚠️ {ticker:<10} | {qty:<12.4f} | Short/Outbound Position")
                
    print("-" * 55)
    
    # 4. Net Worth Asset Class Allocation Breakdown
    total_live_net_worth = live_crypto_value + live_stock_value
    crypto_pct = (live_crypto_value / total_live_net_worth * 100) if total_live_net_worth > 0 else 0
    stock_pct = (live_stock_value / total_live_net_worth * 100) if total_live_net_worth > 0 else 0

    print("\n[ Current Allocation Breakdown ]")
    print(f"🌐 Crypto Portfolio Value: €{live_crypto_value:,.2f} ({crypto_pct:.1f}%)")
    print(f"📈 Equity Portfolio Value: €{live_stock_value:,.2f} ({stock_pct:.1f}%)")
    print(f"💰 Combined Net Worth:     €{total_live_net_worth:,.2f}")

    # 5. Output Calculated Milestones
    print("\n========================= LATEST PORTFOLIO MILESTONES =========================")
    for day in historical_timeline[-3:]:
        # Note: If total_invested_eur doesn't match total investments, it needs fixing in analyzer.py
        print(f"Date: {day['date']} | Total Net Worth: €{day['total_portfolio_value_eur']:,} | Total Invested: €{day['total_invested_eur']:,} | ROI: {day['roi_percentage']}%")
        
        # Core Crypto Watchlist tracking
        core_tracked = ['BTC', 'ETH', 'ADA', 'BNB', 'SOL', 'LINK', 'XRP']
        for asset in core_tracked:
            if asset in day['assets']:
                data = day['assets'][asset]
                print(f"   -> {asset:<5}: Bal: {data['balance']:<10.4f} | Avg Buy: €{data['avg_buy_price']:<8.2f} | Profit/Share: €{data['profit_per_share']:.2f}")
                
    print("===============================================================================\n")

    # 6. Boot up the Conversational AI Interface Agent
    agent = SentinelAnalyst(historical_data=historical_timeline)
    agent.start_chat_loop()

if __name__ == "__main__":
    main()