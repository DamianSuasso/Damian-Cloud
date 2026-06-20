import sys
from connectors.bitvavo import BitvavoConnector
from Portfolio_tracker.utils.crypto_price_service import Crypto_PriceService
from utils.analyzer import PortfolioAnalyzer
from agents.analyst import SentinelAnalyst

from Portfolio_tracker.sync_crypto import sync_bitvavo
from Portfolio_tracker.sync_cold_wallets import sync_all_wallets
from Portfolio_tracker.sync_stocks import sync_stocks

def main():
    print("=========================================")
    print("      SENTINEL PORTFOLIO CONSOLE         ")
    print("=========================================")

    print("\n[ Initiating Ledger Synchronization Matrix... ]")
    
    # 1. Automatic Auto-Sync on Launch
    try:
        sync_bitvavo()
    except Exception as e:
        print(f"⚠️ Automatic historical ledger update skipped: {e}")

    cold_balances = {}
    
    try:
        # Runs natively, cleanly, and handles its own internal errors exactly like Bitvavo
        cold_balances = sync_all_wallets() or {}
    except Exception as e:
        print(f"⚠️ Automatic cold wallet synchronization skipped: {e}")


    # --- 2. Synchronize Traditional Stock Broker Data ---
    stock_balances = {}
    try:
        stock_balances = sync_stocks() or {}
    except Exception as e:
        print(f"⚠️ Automatic equity broker synchronization skipped: {e}")

    # 2. Fetch Live Snapshot Balances
    print("\n[ Fetching Current Balances... ]")
    bitvavo = BitvavoConnector()
    bv_balances = bitvavo.get_balance()
    
    price_engine = Crypto_PriceService()
    analyzer = PortfolioAnalyzer()
    
    try:
        analyzer.warm_up_price_cache(start_year=2025)
    except Exception as e:
        print(f"⚠️ Cache warming pipeline skipped: {e}")

    print("[ Compiling Portfolio Historical Timeline... ]")
    try:
        # Defaults to processing the entire timeline at a 1-day step interval
        historical_timeline = analyzer.get_portfolio_historical_timeline()
        print(f"✅ Success: Processed {len(historical_timeline)} historical timeline data points.")
    except Exception as e:
        historical_timeline = []
        print(f"⚠️ Failed to compile historical data: {e}")

    print("\n[ Unified Portfolio Snapshot ]")
    print(f"{'SOURCE':<10} | {'ASSET':<6} | {'QTY':<12} | {'VALUE EUR':<10}")
    print("-" * 50)
    
    # --- Process Exchange (Bitvavo) ---
    if isinstance(bv_balances, list):
        for asset in bv_balances:
            # Sum up BOTH liquid and staked allocations safely
            available_qty = float(asset.get('available', 0) or 0)
            staked_qty = float(asset.get('inOrder', 0) or 0)
            total_qty = available_qty + staked_qty
            
            # Use total_qty instead of just available
            if total_qty > 0.0001: 
                symbol = asset['symbol'].upper()  # Force uppercase consistency
                
                # Skip displaying base fiat currency
                if symbol == 'EUR':
                    continue
                    
                price = price_engine.get_eur_price(symbol)
                print(f"EXCHANGE  | {symbol:<6} | {total_qty:<12.4f} | €{total_qty * price:,.2f}")
    
    # --- Process Cold Wallets ---
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)):
            price = price_engine.get_eur_price(coin)
            eur_val = status * price
            print(f"COLD      | {coin:<6} | {status:<12.4f} | €{eur_val:,.2f}")
        else:
            print(f"COLD      | ❌ {coin:<6} | {status}")
            
    print("-" * 50)
    
     # Output the last 3 calculated milestones to confirm success
    print("\n========================= LATEST PORTFOLIO MILESTONES =========================")
    for day in historical_timeline[-3:]:
        print(f"Date: {day['date']} | Total Net Worth: €{day['total_portfolio_value_eur']:,} | Total Invested: €{day['total_invested_eur']:,} | ROI: {day['roi_percentage']}%")
        if 'ADA' in day['assets']:
            ada = day['assets']['ADA']
            print(f"   -> ADA: Bal: {ada['balance']} | Avg Buy: €{ada['avg_buy_price']} | Profit/Share: €{ada['profit_per_share']}")
        if 'BTC' in day['assets']:
            btc = day['assets']['BTC']
            print(f"   -> BTC: Bal: {btc['balance']} | Avg Buy: €{btc['avg_buy_price']} | Profit/Share: €{btc['profit_per_share']}")
        if 'ETH' in day['assets']:
            eth = day['assets']['ETH']
            print(f"   -> ETH: Bal: {eth['balance']} | Avg Buy: €{eth['avg_buy_price']} | Profit/Share: €{eth['profit_per_share']}")
        if 'BNB' in day['assets']:
            bnb = day['assets']['BNB']
            print(f"   -> BNB: Bal: {bnb['balance']} | Avg Buy: €{bnb['avg_buy_price']} | Profit/Share: €{bnb['profit_per_share']}")
        if 'USDT' in day['assets']:
            usdt = day['assets']['USDT']
            print(f"   -> USDT: Bal: {usdt['balance']} | Avg Buy: €{usdt['avg_buy_price']} | Profit/Share: €{usdt['profit_per_share']}")
        if 'LINK' in day['assets']:
            link = day['assets']['LINK']
            print(f"   -> LINK: Bal: {link['balance']} | Avg Buy: €{link['avg_buy_price']} | Profit/Share: €{link['profit_per_share']}")
        if 'XRP' in day['assets']:
            xrp = day['assets']['XRP']
            print(f"   -> XRP: Bal: {xrp['balance']} | Avg Buy: €{xrp['avg_buy_price']} | Profit/Share: €{xrp['profit_per_share']}")
        if 'SOL' in day['assets']:
            sol = day['assets']['SOL']
            print(f"   -> SOL: Bal: {sol['balance']} | Avg Buy: €{sol['avg_buy_price']} | Profit/Share: €{sol['profit_per_share']}")
        if 'USDT' in day['assets']:
            usdt = day['assets']['USDT']
            print(f"   -> USDT: Bal: {usdt['balance']} | Avg Buy: €{usdt['avg_buy_price']} | Profit/Share: €{usdt['profit_per_share']}")
        if 'EUR' in day['assets']:
            eur = day['assets']['EUR']
            print(f"   -> EUR: Bal: {eur['balance']} | Avg Buy: €{eur['avg_buy_price']} | Profit/Share: €{eur['profit_per_share']}")
    print("===============================================================================\n")

    # 3. Boot up the Conversational AI Interface Agent
    agent = SentinelAnalyst(historical_data=historical_timeline)
    agent.start_chat_loop()

if __name__ == "__main__":
    main()