import csv
import os
import hashlib
from utils.db_manager import DatabaseManager

def clean_float(val):
    """Safely converts string numbers to floats, removing quotes or spacing."""
    if not val or str(val).isspace():
        return 0.0
    try:
        # Standardize decimal point from comma formats if needed
        cleaned = str(val).replace('"', '').strip().replace(',', '.')
        return float(cleaned)
    except ValueError:
        return 0.0

def parse_degiro(db_manager, csv_path):
    """Parses DEGIRO transaction export rows."""
    if not os.path.exists(csv_path):
        print("⚠️ DEGIRO statement missing in imports folder. Skipping parse...")
        return
    
    cursor = db_manager.conn.cursor()
    inserted = 0
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # Skip headers
        
        for row in reader:
            if not row or len(row) < 17:
                continue
            
            datum = row[0].strip()
            tijd = row[1].strip()
            product = row[2].strip()
            isin = row[3].strip()
            beurs = row[4].strip()
            aantal = clean_float(row[6])
            koers = clean_float(row[7])
            valuta = row[8].strip() if row[8] else "EUR"
            waarde_eur = clean_float(row[11])
            transactiekosten = clean_float(row[14])
            totaal_eur = clean_float(row[15])
            order_id = row[16].strip()
            
            if not order_id:
                hash_str = f"{datum}_{tijd}_{isin}_{aantal}_{totaal_eur}"
                order_id = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()[:24]
                
            cursor.execute("""
                INSERT OR IGNORE INTO degiro_history (
                    order_id, datum, tijd, product, isin, beurs, 
                    aantal, koers, valuta, waarde_eur, transactiekosten_eur, totaal_eur
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, datum, tijd, product, isin, beurs, aantal, koers, valuta, waarde_eur, transactiekosten, totaal_eur))
            if cursor.rowcount > 0:
                inserted += 1
                
    db_manager.conn.commit()
    print(f"📊 [DEGIRO Engine] Sync complete. Injected {inserted} new unique operations.")

def parse_trade_republic(db_manager, csv_path):
    """Parses Trade Republic export tracking both cash flows and stock acquisitions."""
    if not os.path.exists(csv_path):
        print("⚠️ Trade Republic statement missing in imports folder. Skipping parse...")
        return
        
    cursor = db_manager.conn.cursor()
    inserted = 0
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # Skip header row
        
        for row in reader:
            if not row or len(row) < 18:
                continue
                
            # Clean quotes off every cell right at the start
            row = [cell.replace('"', '').strip() for cell in row]

            # Extract explicitly mapped cells based on Trade Republic's format
            dt = row[0]
            d = row[1]
            acc_type = row[2]
            cat = row[3]
            tx_type = row[4]
            asset_cls = row[5]
            name = row[6]
            symbol = row[7] # This can hold tickers or ISINs depending on asset class
            shares = clean_float(row[8])
            price = clean_float(row[9])
            amount = clean_float(row[10])
            fee = clean_float(row[11])
            tax = clean_float(row[12])
            currency = row[13] if row[13] else "EUR"
            desc = row[17]
            tx_id = row[18]
            
            if not tx_id:
                hash_str = f"{dt}_{symbol}_{shares}_{amount}"
                tx_id = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()[:24]
                
            cursor.execute("""
                INSERT OR IGNORE INTO trade_republic_history (
                    transaction_id, datetime, date, account_type, category, type,
                    asset_class, name, symbol, shares, price, amount, fee, tax, currency, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx_id, dt, d, acc_type, cat, tx_type, asset_cls, name, symbol, shares, price, amount, fee, tax, currency, desc))
            if cursor.rowcount > 0:
                inserted += 1
                
    db_manager.conn.commit()
    print(f"📊 [Trade Republic Engine] Sync complete. Injected {inserted} new unique operations.")

def calculate_stock_balances(db_manager):
    """Aggregates historical transactions from both platforms into a live equity matrix."""
    cursor = db_manager.conn.cursor()
    balances = {}
    
    # 1. Gather net inventory balances from DEGIRO
    cursor.execute("""
        SELECT isin, SUM(aantal) as net_shares 
        FROM degiro_history 
        WHERE isin IS NOT NULL AND isin != ''
        GROUP BY isin
    """)
    for isin, net_shares in cursor.fetchall():
        if net_shares and abs(net_shares) > 0.00001:
            balances[isin] = {"source": "DEGIRO", "shares": net_shares}
            
    # 2. Gather net inventory balances from Trade Republic (Filtering exclusively for SECURITY interactions)
    cursor.execute("""
        SELECT symbol, SUM(shares) as net_shares 
        FROM trade_republic_history 
        WHERE category = 'SECURITY' AND symbol IS NOT NULL AND symbol != ''
        GROUP BY symbol
    """)
    for symbol, net_shares in cursor.fetchall():
        if net_shares and abs(net_shares) > 0.00001:
            # If the stock exists in both brokers, map them cleanly separated by source entity
            if symbol in balances:
                # Merge into a list structure or differentiate key
                balances[f"{symbol} (TR)"] = {"source": "TRADE REPUBLIC", "shares": net_shares}
            else:
                balances[symbol] = {"source": "TRADE REPUBLIC", "shares": net_shares}
                
    return balances

def sync_stocks():
    """Master orchestrator function to clean, process, and return stock inventory portfolios."""
    print("🛰️ Starting complete stock broker offline synchronization matrix...")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    imports_dir = os.path.join(base_dir, "imports")
    
    db = DatabaseManager()
    
    # Run parsing pipelines
    parse_degiro(db, os.path.join(imports_dir, "DEGIRO_Transactions.csv"))
    parse_trade_republic(db, os.path.join(imports_dir, "TRADEREPUBLIC_Transactions.csv"))
    
    # Extract calculations
    stock_portfolio = calculate_stock_balances(db)
    print("✨ ALL STOCK BROKER SYNC OPERATIONS EXECUTED CLEANLY\n")
    return stock_portfolio

if __name__ == "__main__":
    # Test script sandbox execution
    res = sync_stocks()
    print("Current Live Stock Holdings Inventory:")
    for asset, data in res.items():
        print(f" 🏢 {data['source']:<15} | Asset/ISIN: {asset:<15} | Held: {data['shares']:.4f} units")