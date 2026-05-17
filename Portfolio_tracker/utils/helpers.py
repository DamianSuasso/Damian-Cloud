import sqlite3

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

if __name__ == "__main__":
    inspect_database()
    audit_ada_records()