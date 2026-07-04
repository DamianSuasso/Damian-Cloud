import os
from dotenv import load_dotenv
import sqlite3
from Portfolio_tracker.utils.analyzer import PortfolioAnalyzer
from Portfolio_tracker.utils.crypto_price_service import Crypto_PriceService
from Portfolio_tracker.utils.db_manager import DatabaseManager
import requests
import os
import requests

price_engine = Crypto_PriceService()
db = DatabaseManager()
SHARED_DB_PATH = price_engine.db_path
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))



def check_binance_supported_pairs(target_asset="LMWR"):
    url = "https://api.binance.com/api/v3/exchangeInfo"
    target_asset = target_asset.upper().strip()
    
    try:
        print("🔍 Fetching active market registry from Binance API...")
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to communicate with Binance. Status Code: {response.status_code}")
            return
            
        data = response.json()
        symbols_list = data.get("symbols", [])
        
        # Track pairs matched to our specific target, and keep a global set of all base assets
        matched_pairs = []
        all_base_assets = set()
        
        for s in symbols_list:
            # We only care about active SPOT trading markets
            if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", False):
                base = s.get("baseAsset")
                quote = s.get("quoteAsset")
                all_base_assets.add(base)
                
                if base == target_asset or quote == target_asset:
                    matched_pairs.append(f"{base}/{quote}")
        
        print("\n--- RESULTS ---")
        if matched_pairs:
            print(f"✅ Found {len(matched_pairs)} active native pair(s) for {target_asset}:")
            for pair in sorted(matched_pairs):
                print(f"  • {pair}")
        else:
            print(f"❌ '{target_asset}' is NOT natively hosted on Binance Spot markets.")
            # Quick sanity check for close spelling matches
            similar_assets = [asset for asset in all_base_assets if target_asset in asset or asset in target_asset]
            if similar_assets:
                print(f"💡 Did you mean one of these existing assets? {', '.join(sorted(similar_assets))}")
                
        print(f"\n📈 Total unique base assets trading on Binance: {len(all_base_assets)}")
        
    except Exception as e:
        print(f"⚠️ Network check failed: {e}")

def test_portfolio_analyzer(db_path = SHARED_DB_PATH):
   # 1. 📈 Initialize the centralized core engine components
    print("\n[ Initializing Portfolio Analyzer Core Engine... ]")
    analyzer = PortfolioAnalyzer()
    
    # 2. ⚡ Warm up local price storage cache using our centralized class method
    # This automatically handles dynamic asset discovery, table safety checks, and bulk seeding.
    try:
        analyzer.warm_up_price_cache(start_year=2023)
    except Exception as e:
        print(f"⚠️ Cache warming optimization failed: {e}")

    # 3. 📊 Execute your hyper-optimized, single-pass timeline calculation loop
    print("\n📈 Compiling financial tracking sheets...")
    # Using interval_days=7 as your test file originally specified for rapid milestone validation
    history = analyzer.get_portfolio_historical_timeline(interval_days=7)

    # Output the last 3 calculated milestones to confirm success
    print("\n========================= LATEST PORTFOLIO MILESTONES =========================")
    for day in history[-3:]:
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

def inspect_database(db_path = SHARED_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if the table exists first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bitvavo_history';")
    if not cursor.fetchone():
        print("❌ Table 'bitvavo_history' does not exist yet!")
        return

    # Fetch rows matching the new database schema explicitly
    cursor.execute("""
        SELECT id, timestamp, type, asset, amount, fiat_value, fiat_currency, fee, fee_currency 
        FROM bitvavo_history 
        LIMIT 15
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("✨ The database table is currently completely EMPTY.")
        return

    # Print a beautifully structured table header adjusted for currency variances
    print("\n========================= SENTINEL VAULT DB SNAPSHOT =========================")
    header = f"{'TX_ID':<12} | {'TIMESTAMP':<24} | {'TYPE':<10} | {'ASSET':<6} | {'AMOUNT':<10} | {'FIAT_VAL':<10} | {'CURR':<5} | {'FEE':<8}"
    print(header)
    print("-" * len(header))
    
    # Print the individual rows with explicit Type checking for visual clarity
    for row in rows:
        tx_id = str(row[0])[:10] + "..." if row[0] else "None"
        timestamp = str(row[1])[:22] if row[1] else "None"
        tx_type = str(row[2]) if row[2] else "None"
        asset = str(row[3]) if row[3] else "None"
        
        # Format numbers safely
        amount = f"{float(row[4]):.4f}" if row[4] is not None else "None"
        fiat_val = f"{float(row[5]):.2f}" if row[5] is not None else "None"
        fiat_curr = str(row[6]) if row[6] else "None"
        
        # Combine fee metrics for tight alignment
        fee_amt = float(row[7]) if row[7] is not None else 0.0
        fee_curr = str(row[8]) if row[8] else ""
        fee_str = f"{fee_amt:.2f} {fee_curr}".strip() if fee_amt > 0 else "0.00"
        
        print(f"{tx_id:<12} | {timestamp:<24} | {tx_type:<10} | {asset:<6} | {amount:<10} | {fiat_val:<10} | {fiat_curr:<5} | {fee_str:<8}")
    print("==============================================================================\n")
    conn.close()

def audit_ada_records(db_path = SHARED_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Broad check for absolutely anything tracking the ADA asset ticker
    cursor.execute("""
        SELECT id, timestamp, type, asset, amount, fiat_value, fiat_currency, fee, fee_currency 
        FROM bitvavo_history 
        WHERE asset = 'ADA'
        ORDER BY timestamp ASC
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("🔍 Result: No ADA transactions found in the database at all!")
        conn.close()
        return

    print(f"\n📋 FOUND {len(rows)} TOTAL ADA TRANSACTIONS IN DATABASE:")
    header = f"{'TX_ID':<12} | {'TIMESTAMP':<24} | {'TYPE':<10} | {'ASSET':<6} | {'AMOUNT':<10} | {'FIAT_VAL':<10} | {'CURR':<5} | {'FEE':<8}"
    print(header)
    print("-" * len(header))
    
    # Print the individual rows with explicit Type checking for visual clarity
    for row in rows:
        tx_id = str(row[0])[:10] + "..." if row[0] else "None"
        timestamp = str(row[1])[:22] if row[1] else "None"
        tx_type = str(row[2]) if row[2] else "None"
        asset = str(row[3]) if row[3] else "None"
        
        # Format numbers safely
        amount = f"{float(row[4]):.4f}" if row[4] is not None else "None"
        fiat_val = f"{float(row[5]):.2f}" if row[5] is not None else "None"
        fiat_curr = str(row[6]) if row[6] else "None"
        
        # Combine fee metrics for tight alignment
        fee_amt = float(row[7]) if row[7] is not None else 0.0
        fee_curr = str(row[8]) if row[8] else ""
        fee_str = f"{fee_amt:.2f} {fee_curr}".strip() if fee_amt > 0 else "0.00"
        
        print(f"{tx_id:<12} | {timestamp:<24} | {tx_type:<10} | {asset:<6} | {amount:<10} | {fiat_val:<10} | {fiat_curr:<5} | {fee_str:<8}")
    print("==============================================================================\n")
    conn.close()

def audit_full_ada_records(db_path = SHARED_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Unified query merging exchange and on-chain cold wallet history
    query = """
        SELECT 
            id AS tx_id, 
            timestamp, 
            type AS tx_type, 
            'EXCHANGE' AS source, 
            amount, 
            fiat_value, 
            fiat_currency, 
            fee, 
            fee_currency
        FROM bitvavo_history 
        WHERE asset = 'ADA'
        
        UNION ALL
        
        SELECT 
            tx_hash AS tx_id, 
            timestamp, 
            direction AS tx_type, 
            'COLD VAULT' AS source, 
            amount, 
            0.0 AS fiat_value, 
            'EUR' AS fiat_currency, 
            fee, 
            'ADA' AS fee_currency
        FROM cold_wallet_history 
        WHERE coin = 'ADA'
        
        ORDER BY timestamp ASC
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print("🔍 Result: No ADA transactions found across Exchange or Cold Vault tables!")
        conn.close()
        return

    print(f"\n📋 FOUND {len(rows)} TOTAL ADA TRANSACTION CONTEXTS IN SYSTEM:")
    header = f"{'TX_ID':<12} | {'TIMESTAMP':<24} | {'TYPE':<10} | {'LOCATION':<12} | {'AMOUNT':<12} | {'FIAT_VAL':<10} | {'FEE':<10}"
    print(header)
    print("-" * len(header))
    
    for row in rows:
        tx_id = str(row[0])[:10] + "..." if row[0] else "None"
        timestamp = str(row[1])[:22] if row[1] else "None"
        tx_type = str(row[2]) if row[2] else "None"
        source = str(row[3]) if row[3] else "None"
        
        amount = f"{float(row[4]):.4f} ADA" if row[4] is not None else "None"
        fiat_val = f"€{float(row[5]):.2f}" if row[5] is not None else "None"
        
        # Format custom fees depending on if it's exchange cash or on-chain network gas
        fee_amt = float(row[7]) if row[7] is not None else 0.0
        fee_curr = str(row[8]) if row[8] else ""
        fee_str = f"{fee_amt:.4f} {fee_curr}".strip() if fee_amt > 0 else "0.00"
        
        print(f"{tx_id:<12} | {timestamp:<24} | {tx_type:<10} | {source:<12} | {amount:<12} | {fiat_val:<10} | {fee_str:<10}")
    print("==============================================================================\n")
    conn.close()

def inspect_cold_wallets(db_path = SHARED_DB_PATH):
    """NEW: Reads the blockchain history entries mapped into the system"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cold_wallet_history';")
    if not cursor.fetchone():
        print("❌ Table 'cold_wallet_history' does not exist yet!")
        return

    cursor.execute("""
        SELECT tx_hash, timestamp, coin, direction, amount, fee, block_height 
        FROM cold_wallet_history 
        ORDER BY timestamp DESC 
        LIMIT 150
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("✨ On-chain wallet table exists but is currently completely EMPTY.")
        return

    print("======================== COLD WALLET ON-CHAIN SNAPSHOT ========================")
    wallet_header = f"{'TX_HASH':<14} | {'TIMESTAMP':<24} | {'COIN':<5} | {'DIRECTION':<10} | {'AMOUNT':<12} | {'FEE':<10} | {'BLOCK':<8}"
    print(wallet_header)
    print("-" * len(wallet_header))
    
    for row in rows:
        tx_hash = str(row[0])[:11] + "..." if row[0] else "None"
        timestamp = str(row[1])[:22] if row[1] else "None"
        coin = str(row[2]) if row[2] else "None"
        direction = str(row[3]) if row[3] else "None"
        
        # Format decimals dynamically to accommodate both high-value BTC and smaller gas weights
        amount = f"{float(row[4]):.6f}" if row[4] is not None else "None"
        fee = f"{float(row[5]):.6f}" if row[5] is not None else "0.000000"
        block = int(row[6]) if row[6] is not None else 0
        
        print(f"{tx_hash:<14} | {timestamp:<24} | {coin:<5} | {direction:<10} | {amount:<12} | {fee:<10} | {block:<8}")
    print("===============================================================================\n")
    conn.close()

def print_directory_tree(start_path=".", ignore_dirs=None):
    """Generates a clean text-based directory tree matching engineering project layouts."""
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv'}
        
    print(f"📁 Root: {os.path.abspath(start_path)}\n")
    
    for root, dirs, files in os.walk(start_path):
        # Filter out ignored directories in-place so os.walk skips them
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        # Calculate depth to manage branching visuals
        level = root.replace(start_path, '').count(os.sep)
        indent = '   ' * level
        
        # Print the current directory name (except for the root start folder)
        if root != start_path:
            print(f"{indent}├── 📂 {os.path.basename(root)}/")
            
        # Print files inside this directory folder
        sub_indent = '   ' * (level + 1)
        for f in files:
            print(f"{sub_indent}├── 📄 {f}")


if __name__ == "__main__":
    # check_binance_supported_pairs("LMWR")
    test_portfolio_analyzer()
    # inspect_database()
    # audit_full_ada_records()
    # audit_ada_records()
    # inspect_cold_wallets()
    # print_directory_tree()