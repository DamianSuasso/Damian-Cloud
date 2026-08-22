from datetime import datetime, timedelta
import sqlite3
from typing import Union, List, Dict, Any, Tuple


def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """Generates a list of YYYY-MM-DD strings from start_date to end_date (inclusive)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    step = timedelta(days=1)
    
    dates = []
    while start <= end:
        dates.append(start.strftime("%Y-%m-%d"))
        start += step
    return dates

def get_missing_price_dates(db_obj: Any, asset: str, start_date: str, end_date: str, asset_type: str = 'STOCK') -> List[str]:
    """
    Compares the required date range against cached dates in SQLite 
    and returns a list of missing dates for the given asset.
    Accepts either a DatabaseManager (with .conn) or direct sqlite3.Connection.
    """
    required_dates = set(generate_date_range(start_date, end_date))
    conn = db_obj.conn if hasattr(db_obj, 'conn') else db_obj
    
    query = "SELECT date FROM historical_prices WHERE asset = ? AND asset_type = ?"
    cursor = conn.cursor()
    cursor.execute(query, (asset, asset_type))
    cached_dates = {row[0] for row in cursor.fetchall()}
    cursor.close()
        
    missing = sorted(list(required_dates - cached_dates))
    return missing

def batch_save_prices(db_obj: Any, price_records: List[Tuple[str, str, str, float, float]]):
    """
    Executes a high-performance batch insert/update for price records.
    price_records format: [(asset, asset_type, date, price_eur, price_usdt), ...]
    """
    if not price_records:
        return
        
    conn = db_obj.conn if hasattr(db_obj, 'conn') else db_obj
    query = """
    INSERT INTO historical_prices (asset, asset_type, date, price_eur, price_usdt)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(asset, asset_type, date) DO UPDATE SET 
        price_eur=excluded.price_eur,
        price_usdt=excluded.price_usdt
    """
    cursor = conn.cursor()
    cursor.executemany(query, price_records)
    conn.commit()
    cursor.close()

def get_historical_eur_usdt_rate(
    db: Union[sqlite3.Connection, str, Any], 
    date_str: str, 
    default_rate: float = 1.085
) -> float:
    """
    Fetches the historical EUR/USDT cross-rate on a given date using BTC historical 
    prices as a proxy (price_usdt / price_eur). Falls back to default_rate if missing.
    Accepts either a DatabaseManager instance, active sqlite3.Connection, or file path string.
    """
    conn = None
    should_close = False

    try:
        if isinstance(db, str):
            conn = sqlite3.connect(db, check_same_thread=False)
            should_close = True
        elif hasattr(db, 'conn'):
            conn = db.conn
        else:
            conn = db

        cursor = conn.cursor()
        cursor.execute("""
            SELECT price_usdt / price_eur 
            FROM historical_prices 
            WHERE asset = 'BTC' 
              AND date = ? 
              AND price_eur > 0
        """, (date_str,))
        row = cursor.fetchone()
        cursor.close()

        if row and row[0] is not None:
            return float(row[0])
        return default_rate

    except Exception:
        return default_rate
    finally:
        if should_close and conn:
            conn.close()

def calculate_cost_basis_summary(transactions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculates portfolio position cost basis metrics from a chronological list of transactions.
    
    Expected transaction format:
    [
        {
            'type': 'BUY' | 'SELL',
            'amount': float,          # Quantity of units
            'price_eur': float,       # Price per unit in EUR
            'price_usdt': float,      # Price per unit in USDT
            'fee_eur': float,         # Optional fee
            'fee_usdt': float         # Optional fee
        }, ...
    ]
    """
    total_quantity = 0.0
    total_cost_eur = 0.0
    total_cost_usdt = 0.0
    realized_pnl_eur = 0.0
    realized_pnl_usdt = 0.0

    for tx in transactions:
        tx_type = tx.get('type', '').upper()
        amount = float(tx.get('amount', 0.0))
        price_eur = float(tx.get('price_eur', 0.0))
        price_usdt = float(tx.get('price_usdt', 0.0))
        fee_eur = float(tx.get('fee_eur', 0.0))
        fee_usdt = float(tx.get('fee_usdt', 0.0))

        if tx_type == 'BUY':
            total_quantity += amount
            total_cost_eur += (amount * price_eur) + fee_eur
            total_cost_usdt += (amount * price_usdt) + fee_usdt

        elif tx_type == 'SELL' and total_quantity > 0:
            avg_cost_eur = total_cost_eur / total_quantity
            avg_cost_usdt = total_cost_usdt / total_quantity

            sell_quantity = min(amount, total_quantity)
            
            proceeds_eur = (sell_quantity * price_eur) - fee_eur
            proceeds_usdt = (sell_quantity * price_usdt) - fee_usdt

            realized_pnl_eur += proceeds_eur - (sell_quantity * avg_cost_eur)
            realized_pnl_usdt += proceeds_usdt - (sell_quantity * avg_cost_usdt)

            total_quantity -= sell_quantity
            total_cost_eur -= (sell_quantity * avg_cost_eur)
            total_cost_usdt -= (sell_quantity * avg_cost_usdt)

            if total_quantity <= 0:
                total_quantity = 0.0
                total_cost_eur = 0.0
                total_cost_usdt = 0.0

    avg_unit_cost_eur = (total_cost_eur / total_quantity) if total_quantity > 0 else 0.0
    avg_unit_cost_usdt = (total_cost_usdt / total_quantity) if total_quantity > 0 else 0.0

    return {
        'total_quantity': total_quantity,
        'total_cost_eur': round(total_cost_eur, 4),
        'total_cost_usdt': round(total_cost_usdt, 4),
        'avg_unit_cost_eur': round(avg_unit_cost_eur, 4),
        'avg_unit_cost_usdt': round(avg_unit_cost_usdt, 4),
        'realized_pnl_eur': round(realized_pnl_eur, 4),
        'realized_pnl_usdt': round(realized_pnl_usdt, 4)
    }

def sync_all_portfolio_prices(db_manager: Any, stock_service: Any, crypto_service: Any, default_start_date: str = "2020-01-01"):
    """
    Master Orchestrator: Discovers all distinct assets across holdings/transactions 
    and triggers bulk price fetches up to today.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = db_manager.conn if hasattr(db_manager, 'conn') else db_manager

    try:
        # Fetch unique assets and their asset_type from the DB
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT asset, asset_type FROM historical_prices")
        assets = cursor.fetchall()  # List of tuples: [('AAPL', 'STOCK'), ('BTC', 'CRYPTO'), ...]
        cursor.close()

        print(f"🚀 [FinancialUtils] Starting master portfolio price sync for {len(assets)} assets up to {today_str}...")

        for asset, asset_type in assets:
            if not asset:
                continue
                
            if asset_type == 'STOCK' and stock_service:
                stock_service.fetch_and_cache_range(asset, default_start_date, today_str)
            elif asset_type == 'CRYPTO' and crypto_service:
                crypto_service.fetch_and_cache_range(asset, default_start_date, today_str)

        print("✅ [FinancialUtils] Master price sync complete.")

    except Exception as e:
        print(f"⚠️ [FinancialUtils] Error in sync_all_portfolio_prices: {e}")