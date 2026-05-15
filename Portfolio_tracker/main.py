from connectors.bitvavo import BitvavoConnector
from connectors.wallet_tracker import WalletTracker
from utils.price_service import PriceService

def main():
    print("--- Sentinel Portfolio Tracker ---")
    
    # 1. Fetch Data
    bitvavo = BitvavoConnector()
    bv_balances = bitvavo.get_balance() # List of dicts
    
    tracker = WalletTracker()
    cold_balances = tracker.get_all_balances() # Dict of {Coin: Value/Error}
    
    # 2. Initialize Price Service
    price_engine = PriceService()
    
    print("\n[ Unified Portfolio Snapshot ]")
    
    # --- Process Exchange (Bitvavo) ---
    print(f"{'SOURCE':<10} | {'ASSET':<6} | {'QTY':<12} | {'VALUE EUR':<10}")
    print("-" * 50)
    
    if isinstance(bv_balances, list):
        for asset in bv_balances:
            qty = float(asset.get('available', 0))
            if qty > 0:
                symbol = asset['symbol']
                price = price_engine.get_eur_price(symbol)
                print(f"EXCHANGE  | {symbol:<6} | {qty:<12.4f} | €{qty*price:,.2f}")
    
    # --- Process Cold Wallets (Your Requested Loop) ---
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)):
            price = price_engine.get_eur_price(coin)
            eur_val = status * price
            print(f"COLD      | {coin:<6} | {status:<12.4f} | €{eur_val:,.2f}")
        else:
            # This prints your ❌ error messages
            print(f"COLD      | ❌ {coin:<6} | {status}")

if __name__ == "__main__":
    main()