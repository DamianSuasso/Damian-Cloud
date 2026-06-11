import sqlite3
from utils.analyzer import PortfolioAnalyzer
from utils.price_service import PriceService

def test_portfolio_analyzer():
    price_engine = PriceService()
    db_path = price_engine.db_path  # Access the same database path used by the price service
    
    # 1. 🔍 Dynamically extract every unique asset across both transaction logs
    print("📋 Scanning database for active assets...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 🔍 Debug: Let's see what tables actually exist in this file right now
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]
        print(f"🗄️ Tables found inside '{db_path}': {existing_tables}")
        
        # Build the asset list dynamically based on what tables are actually ready
        target_assets = []
        
        if 'bitvavo_history' in existing_tables:
            cursor.execute("SELECT DISTINCT asset FROM bitvavo_history WHERE asset IS NOT NULL AND asset != 'EUR' AND asset != ''")
            target_assets.extend([row[0] for row in cursor.fetchall()])
        else:
            print("⚠️ 'bitvavo_history' table not found in this file.")
            
        if 'cold_wallet_history' in existing_tables:
            cursor.execute("SELECT DISTINCT coin AS asset FROM cold_wallet_history WHERE coin IS NOT NULL AND coin != 'EUR' AND coin != ''")
            target_assets.extend([row[0] for row in cursor.fetchall()])
        else:
            print("ℹ️ 'cold_wallet_history' table does not exist yet (skipping on-chain search).")
            
        # De-duplicate the combined list
        target_assets = list(set(target_assets))
        conn.close()
        
        print(f"🎯 Total unique assets discovered: {', '.join(target_assets) if target_assets else 'None'}")
        
    except Exception as e:
        print(f"⚠️ Failed to scan asset tables automatically: {e}")
        target_assets = ['BTC', 'ETH', 'ADA']

    # 2. Bulk pre-seed everything discovered
    print("\n⚡ Warming up local price storage cache via bulk channels...")
    for asset in target_assets:
        price_engine.seed_historical_prices_bulk(asset, start_year=2020)
        
    # 3. Execute your hyper-optimized, single-pass timeline calculation loop
    print("\n📈 Compiling financial tracking sheets...")
    analyzer = PortfolioAnalyzer()
    history = analyzer.get_portfolio_historical_timeline(interval_days=7)

    # Output the last 3 calculated milestones to confirm success
    print("\n========================= LATEST PORTFOLIO MILESTONES =========================")
    for day in history[-3:]:
        print(f"Date: {day['date']} | Total Net Worth: €{day['total_portfolio_value_eur']:,} | Total Invested: €{day['total_invested_eur']:,} | ROI: {day['roi_percentage']}%")
        if 'ADA' in day['assets']:
            ada = day['assets']['ADA']
            print(f"   -> ADA: Bal: {ada['balance']} | Avg Buy: €{ada['avg_buy_price']} | Profit/Share: €{ada['profit_per_share']}")
    print("===============================================================================\n")

def inspect_database():
    conn = sqlite3.connect("sentinel_vault.db")
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

def audit_ada_records():
    conn = sqlite3.connect("sentinel_vault.db")
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

def audit_full_ada_records():
    conn = sqlite3.connect("sentinel_vault.db")
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

def inspect_cold_wallets():
    """NEW: Reads the blockchain history entries mapped into the system"""
    conn = sqlite3.connect("sentinel_vault.db")
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
import os

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
    test_portfolio_analyzer()
    inspect_database()
    audit_full_ada_records()
    audit_ada_records()
    inspect_cold_wallets()
    print_directory_tree()