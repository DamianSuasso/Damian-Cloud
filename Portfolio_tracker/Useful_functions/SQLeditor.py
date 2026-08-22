import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Path Injection ---
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up 2 levels: 'Usefull functions' -> 'Portfolio_tracker' -> 'Damian-Cloud'
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from Portfolio_tracker.utils.db_manager import DatabaseManager

db = DatabaseManager()
conn = db.conn

cursor = conn.cursor()

# 1. Clean up potential duplicate historical entries
cursor.execute("""
    DELETE FROM historical_prices
    WHERE rowid NOT IN (
        SELECT MAX(rowid)
        FROM historical_prices
        GROUP BY asset, asset_type, date
    );
""")

# 2. Create the composite unique index
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_historical_prices_asset_type_date 
    ON historical_prices (asset, asset_type, date);
""")

conn.commit()
cursor.close()

print("✅ Existing duplicates cleaned and unique index created successfully!")