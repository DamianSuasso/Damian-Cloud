import sqlite3
from datetime import datetime
from Portfolio_tracker.connectors.bitvavo import BitvavoConnector
from Portfolio_tracker.utils.db_manager import DatabaseManager

def get_latest_stored_timestamp():
    """Queries the database to find the timestamp of the newest recorded transaction."""
    db = DatabaseManager()
    cursor = db.conn.cursor()
    
    # Select the newest transaction based on chronological execution time
    cursor.execute("SELECT timestamp FROM bitvavo_history ORDER BY timestamp DESC LIMIT 1")
    row = cursor.fetchone()
    
    if row and row[0]:
        iso_str = row[0]
        try:
            # Handle standard ISO timestamp variations (e.g., converting 'Z' for fromisoformat)
            clean_ts = iso_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_ts)
            # Bitvavo API expects fromDate as a Unix timestamp string in MILLISECONDS
            return str(int(dt.timestamp() * 1000))
        except Exception as e:
            print(f"⚠️ Error parsing last timestamp formatting: {e}")
            return "0"
    return "0" # If DB is empty, default to beginning of time

def sync_bitvavo():
    print("🔄 Connecting to Bitvavo to fetch historical data...")
    bv = BitvavoConnector()
    db = DatabaseManager()
    
    # 1. Determine where our local database left off
    from_date_ms = get_latest_stored_timestamp()
    
    if from_date_ms != "0":
        print(f"⏱️ Requesting new ledger entries since last sync milestone...")
    else:
        print("📥 Local database is empty. Extracting entire account lifecycle...")

    # 2. Grab only the new delta history from the connector
    history = bv.get_transaction_history(from_date=from_date_ms)
    
    # 3. Save to database if new records are found
    if history:
        print(f"✅ Found {len(history)} new historical events.")
        db.save_transactions(history)
        print("💾 New history saved to database.")
    elif history == []:
        print("✅ Database is already fully sync-locked. No new entries found.")
    else:
        print("❌ Could not fetch history. Check API permissions or mock configurations.")

if __name__ == "__main__":
    sync_bitvavo()