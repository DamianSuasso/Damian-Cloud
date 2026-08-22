import csv
import os
import hashlib
import requests
from Portfolio_tracker.utils.db_manager import DatabaseManager

RESOLVED_TICKERS_CACHE = {}
RESOLVED_SECTORS_CACHE = {}

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

_db_map_client = DatabaseManager()

def resolve_ticker_and_sector(identifier: str) -> tuple[str, str]:
    """
    Resolves an identifier to a Yahoo ticker and its market sector.
    Checks memory first, then local SQLite cache, and falls back to the API.
    """
    identifier = identifier.strip().upper()
    if not identifier:
        return "", "Other"

    # 1. Memory Check
    if identifier in RESOLVED_TICKERS_CACHE:
        return RESOLVED_TICKERS_CACHE[identifier], RESOLVED_SECTORS_CACHE.get(identifier, "Other")

    # 2. Database Check
    try:
        cursor = _db_map_client.conn.cursor()
        cursor.execute("SELECT resolved_ticker, sector FROM asset_ticker_map WHERE identifier = ? LIMIT 1", (identifier,))
        row = cursor.fetchone()
        cursor.close()
        if row and row[0]:
            ticker, sector = row[0].upper(), row[1] or "Other"
            RESOLVED_TICKERS_CACHE[identifier] = ticker
            RESOLVED_SECTORS_CACHE[identifier] = sector
            return ticker, sector
    except Exception as e:
        print(f"⚠️ [SyncStocks] Local ticker map lookup error: {e}")

    # Native Short Symbol short-circuit baseline
    resolved_ticker = identifier
    if len(identifier) <= 5 and identifier.isalpha():
        resolved_ticker = identifier

    # 3. API Query Layer (Fetches both Ticker and Sector in ONE hit)
    print(f"🔍 [SyncStocks] [API Lookup] Cache miss. Fetching complete metadata directory for: '{identifier}'...")
    sector = "Other"
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={identifier}&quotesCount=1&newsCount=0"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get("quotes", [])
            if quotes:
                resolved_ticker = quotes[0].get("symbol", resolved_ticker).upper()
                sector = quotes[0].get("sector", "Other") or "Other"
                print(f"🎯 [SyncStocks] [API Match] Resolved '{identifier}' ➡️ Ticker: '{resolved_ticker}' | Sector: '{sector}'")
                
                # Commit to DB
                cursor = _db_map_client.conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO asset_ticker_map (identifier, resolved_ticker, sector)
                    VALUES (?, ?, ?)
                """, (identifier, resolved_ticker, sector))
                _db_map_client.conn.commit()
                cursor.close()
    except Exception as e:
        print(f"⚠️ [SyncStocks] [API Lookup Failed] Metadata trace blocked for '{identifier}': {e}")

    RESOLVED_TICKERS_CACHE[identifier] = resolved_ticker
    RESOLVED_SECTORS_CACHE[identifier] = sector
    return resolved_ticker, sector

def parse_degiro(db_manager, csv_path):
    """Parses DEGIRO transaction export rows."""
    if not os.path.exists(csv_path):
        print("⚠️ [SyncStocks] DEGIRO statement missing in imports folder. Skipping parse...")
        return
    
    cursor = db_manager.conn.cursor()
    inserted = 0
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) 
        for row in reader:
            if not row or len(row) < 17:
                continue
            datum, tijd, product, isin, beurs = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()
            aantal, koers = clean_float(row[6]), clean_float(row[7])
            valuta = row[8].strip() if row[8] else "EUR"
            waarde_eur, transactiekosten, totaal_eur = clean_float(row[11]), clean_float(row[14]), clean_float(row[15])
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
    print(f"📊 [SyncStocks] [DEGIRO Engine] Sync complete. Injected {inserted} new operations.")

def parse_trade_republic(db_manager, csv_path):
    """Parses Trade Republic export tracking both cash flows and stock acquisitions."""
    if not os.path.exists(csv_path):
        print("⚠️ [SyncStocks] Trade Republic statement missing in imports folder. Skipping parse...")
        return
        
    cursor = db_manager.conn.cursor()
    inserted = 0
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if not row or len(row) < 18:
                continue
            row = [cell.replace('"', '').strip() for cell in row]
            dt, d, acc_type, cat, tx_type, asset_cls, name, symbol = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
            shares, price, amount, fee, tax = clean_float(row[8]), clean_float(row[9]), clean_float(row[10]), clean_float(row[11]), clean_float(row[12])
            currency, desc, tx_id = row[13] if row[13] else "EUR", row[17], row[18]
            
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
    print(f"📊 [SyncStocks] [Trade Republic Engine] Sync complete. Injected {inserted} new operations.")

def calculate_stock_balances(db_manager):
    """Aggregates historical transactions and triggers metadata mapping."""
    cursor = db_manager.conn.cursor()
    balances = {}
    
    # 1. DEGIRO Processing
    cursor.execute("SELECT isin, SUM(aantal) FROM degiro_history WHERE isin != '' GROUP BY isin")
    for isin, net_shares in cursor.fetchall():
        if net_shares and abs(net_shares) > 0.00001:
            ticker, _ = resolve_ticker_and_sector(isin)
            balances[ticker] = balances.get(ticker, 0.0) + net_shares
            
    # 2. Trade Republic Processing
    cursor.execute("SELECT symbol, SUM(shares) FROM trade_republic_history WHERE category = 'SECURITY' AND symbol != '' GROUP BY symbol")
    for symbol, net_shares in cursor.fetchall():
        if net_shares and abs(net_shares) > 0.00001:
            ticker, _ = resolve_ticker_and_sector(symbol)
            balances[ticker] = balances.get(ticker, 0.0) + net_shares
                
    return {ticker: {"shares": shares} for ticker, shares in balances.items()}

def sync_stocks():
    """Master orchestrator function."""
    print("🛰️ [SyncStocks] Starting complete stock broker offline synchronization matrix...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    imports_dir = os.path.join(base_dir, "imports")
    db = DatabaseManager()
    
    parse_degiro(db, os.path.join(imports_dir, "DEGIRO_Transactions.csv"))
    parse_trade_republic(db, os.path.join(imports_dir, "TRADEREPUBLIC_Transactions.csv"))
    
    stock_portfolio = calculate_stock_balances(db)
    print("✨ [SyncStocks] ALL STOCK BROKER SYNC OPERATIONS EXECUTED CLEANLY\n")
    return stock_portfolio

if __name__ == "__main__":
    res = sync_stocks()