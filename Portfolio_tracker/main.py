import sys
from connectors.bitvavo import BitvavoConnector
from utils.price_service import PriceService
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
    
    price_engine = PriceService()
    analyzer = PortfolioAnalyzer()
    
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
    
    # 3. Boot up the Conversational AI Interface Agent
    agent = SentinelAnalyst()
    agent.start_chat_loop()

if __name__ == "__main__":
    main()