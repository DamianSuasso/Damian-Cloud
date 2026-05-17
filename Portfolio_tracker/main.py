import sys
from connectors.bitvavo import BitvavoConnector
from connectors.wallet_tracker import WalletTracker
from utils.price_service import PriceService
from utils.analyzer import PortfolioAnalyzer
from sync_history import sync_bitvavo
from agents.analyst import SentinelAnalyst

def main():
    print("=========================================")
    print("      SENTINEL PORTFOLIO CONSOLE         ")
    print("=========================================")
    
    # 1. Automatic Auto-Sync on Launch
    try:
        sync_bitvavo()
    except Exception as e:
        print(f"⚠️ Automatic historical ledger update skipped: {e}")

    # 2. Fetch Live Snapshot Balances
    print("\n[ Fetching Current Balances... ]")
    bitvavo = BitvavoConnector()
    bv_balances = bitvavo.get_balance()
    
    tracker = WalletTracker()
    cold_balances = tracker.get_all_balances()
    
    price_engine = PriceService()
    analyzer = PortfolioAnalyzer()
    
    print("\n[ Unified Portfolio Snapshot ]")
    print(f"{'SOURCE':<10} | {'ASSET':<6} | {'QTY':<12} | {'VALUE EUR':<10}")
    print("-" * 50)
    
    # --- Process Exchange (Bitvavo) ---
    if isinstance(bv_balances, list):
        for asset in bv_balances:
            qty = float(asset.get('available', 0))
            if qty > 0:
                symbol = asset['symbol']
                price = price_engine.get_eur_price(symbol)
                print(f"EXCHANGE  | {symbol:<6} | {qty:<12.4f} | €{qty*price:,.2f}")
    
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