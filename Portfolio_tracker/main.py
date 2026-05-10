import os
from connectors.bitvavo import BitvavoConnector
from connectors.wallet_tracker import WalletTracker

def main():
    print("--- Sentinel Portfolio Tracker ---")
    
    # 1. Bitvavo
    bitvavo = BitvavoConnector()
    bv_balances = bitvavo.get_balance()
    
    # 2. Cold Wallets
    wallets = WalletTracker()
    cold_balances = wallets.get_all_balances()
    
    print("\n[ Unified Portfolio Snapshot ]")
    
    # Process Exchanges
    if not bv_balances:
        print("EXCHANGE | ❌ Bitvavo: Sync Error / No Access")
    else:
        for asset in bv_balances:
            if float(asset.get('available', 0)) > 0:
                print(f"EXCHANGE | {asset['symbol']}: {asset['available']}")

    # Process Cold Wallets
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)):
            print(f"COLD     | {coin}: {status}")
        else:
            print(f"COLD     | ❌ {coin}: {status}")

if __name__ == "__main__":
    main()