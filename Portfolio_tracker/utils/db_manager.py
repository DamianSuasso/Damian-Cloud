import os
import sqlite3

class DatabaseManager:
    def __init__(self, db_name="sentinel_vault.db"):
        # 1. Get the absolute path of the directory containing this script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Back up one level to find the Portfolio_tracker/ root directory
        portfolio_tracker_dir = os.path.dirname(base_dir)

        # 3. Define your dedicated database directory path
        db_dir = os.path.join(portfolio_tracker_dir, "database")
        
        # 4. Create the database directory automatically if it doesn't exist yet
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        # 5. Bind the connection to the explicit absolute path
        self.db_path = os.path.join(db_dir, db_name)
        self.conn = sqlite3.connect(self.db_path)
        
        self.create_tables()

    def create_tables(self):
        # 1. Bitvavo History Layout
        query_bitvavo = """
        CREATE TABLE IF NOT EXISTS bitvavo_history (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            type TEXT,              -- buy, sell, staking, deposit, withdrawal
            asset TEXT,             -- e.g., BTC, ETH, EUR
            amount REAL,            -- Quantity of the asset
            fiat_value REAL,        -- Total cash/stablecoin value equivalent
            fiat_currency TEXT,     -- EUR, USDC, USDT, etc.
            fee REAL,
            fee_currency TEXT
        )
        """
        self.conn.execute(query_bitvavo)
        
        # 2. Dedicated Cold Wallet On-Chain History Layout
        query_cold_wallet = """
        CREATE TABLE IF NOT EXISTS cold_wallet_history (
            tx_hash TEXT PRIMARY KEY,   -- On-chain unique Transaction Hash/ID
            timestamp TEXT,             -- Block execution time (ISO format)
            coin TEXT,                  -- BTC, ETH, XRP, etc.
            wallet_address TEXT,        -- The public key address tracked
            direction TEXT,             -- INBOUND (Deposit) or OUTBOUND (Withdrawal/Spend)
            amount REAL,                -- Pure crypto quantity transferred
            fee REAL,                   -- On-chain network gas/miner fee paid
            block_height INTEGER        -- Useful for calculating network confirmations
        )
        """
        self.conn.execute(query_cold_wallet)

        # 3. Dedicated DEGIRO Broker Table Layout
        query_degiro = """
        CREATE TABLE IF NOT EXISTS degiro_history (
            order_id TEXT PRIMARY KEY,
            datum TEXT,
            tijd TEXT,
            product TEXT,
            isin TEXT,
            beurs TEXT,
            aantal REAL,
            koers REAL,
            valuta TEXT,
            waarde_eur REAL,
            transactiekosten_eur REAL,
            totaal_eur REAL
        )
        """
        self.conn.execute(query_degiro)

        # 4. Dedicated Trade Republic Table Layout
        query_tr = """
        CREATE TABLE IF NOT EXISTS trade_republic_history (
            transaction_id TEXT PRIMARY KEY,
            datetime TEXT,
            date TEXT,
            account_type TEXT,
            category TEXT,
            type TEXT,
            asset_class TEXT,
            name TEXT,
            symbol TEXT,
            shares REAL,
            price REAL,
            amount REAL,
            fee REAL,
            tax REAL,
            currency TEXT,
            description TEXT
        )
        """
        self.conn.execute(query_tr)

        # 5. Centralized Twin-Currency Pricing Engine Cache Matrix
        query_prices = """
        CREATE TABLE IF NOT EXISTS historical_prices (
            asset TEXT NOT NULL,
            asset_type TEXT NOT NULL,  -- 🆕 'STOCK' or 'CRYPTO'
            date TEXT NOT NULL,
            price_eur REAL,
            price_usdt REAL,
            PRIMARY KEY (asset, asset_type, date) -- ⚡ FIXED: Compound identity matches asset class
        )
        """
        self.conn.execute(query_prices)

        # 6. 🆕 Persistent Ticker Translation Directory Map Cache
        query_ticker_map = """
        CREATE TABLE IF NOT EXISTS asset_ticker_map (
            identifier TEXT PRIMARY KEY,  -- The input ISIN or raw broker description string
            resolved_ticker TEXT NOT NULL,  -- The verified canonical Yahoo market ticker symbol
            sector TEXT DEFAULT 'Unknown'   -- Market sector for stock asset classification
        )
        """
        self.conn.execute(query_ticker_map)

        # Performance optimization index for your dashboard SQL Joins later
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_map_resolved ON asset_ticker_map(resolved_ticker);")
        
        self.conn.commit()

    def save_transactions(self, transactions):
        query = """
        INSERT OR IGNORE INTO bitvavo_history 
        (id, timestamp, type, asset, amount, fiat_value, fiat_currency, fee, fee_currency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for tx in transactions:
            tx_type = tx.get('type', '').lower()
            
            # Flawless multi-currency routing based on asset flows
            if tx_type == 'buy':
                asset = tx.get('receivedCurrency')
                amount = tx.get('receivedAmount')
                fiat_value = tx.get('sentAmount')
                fiat_currency = tx.get('sentCurrency') 
            elif tx_type == 'sell':
                asset = tx.get('sentCurrency')
                amount = tx.get('sentAmount')
                fiat_value = tx.get('receivedAmount')
                fiat_currency = tx.get('receivedCurrency') 
            elif tx_type in ['staking', 'distribution']:
                asset = tx.get('receivedCurrency')
                amount = tx.get('receivedAmount')
                fiat_value = 0.0
                fiat_currency = 'EUR' 
            elif tx_type in ['deposit', 'withdrawal']:
                asset = tx.get('receivedCurrency') or tx.get('sentCurrency')
                amount = tx.get('receivedAmount') or tx.get('sentAmount')
                if asset == 'EUR':
                    fiat_value = amount
                    fiat_currency = 'EUR'
                else:
                    fiat_value = None
                    fiat_currency = None
            else:
                asset = tx.get('receivedCurrency') or tx.get('sentCurrency')
                amount = tx.get('receivedAmount') or tx.get('sentAmount')
                fiat_value = None
                fiat_currency = None

            # Typecast safely
            safe_amount = float(amount) if amount is not None else 0.0
            safe_fiat = float(fiat_value) if fiat_value is not None else 0.0
            safe_fee = float(tx.get('feesAmount', 0.0)) if tx.get('feesAmount') is not None else 0.0

            self.conn.execute(query, (
                tx.get('transactionId') or tx.get('id'),
                tx.get('executedAt') or tx.get('timestamp'),
                tx_type,
                asset,
                safe_amount,
                safe_fiat,
                fiat_currency,
                safe_fee,
                tx.get('feesCurrency')
            ))
        self.conn.commit()

    def save_cold_wallet_transactions(self, transactions):
        """Saves a batch of parsed on-chain history entries safely."""
        query = """
        INSERT OR IGNORE INTO cold_wallet_history 
        (tx_hash, timestamp, coin, wallet_address, direction, amount, fee, block_height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        for tx in transactions:
            self.conn.execute(query, (
                tx['tx_hash'],
                tx['timestamp'],
                tx['coin'],
                tx['wallet_address'],
                tx['direction'],
                tx['amount'],
                tx['fee'],
                tx['block_height']
            ))
        self.conn.commit()

    def get_calculated_balance_for_coin(self, coin_ticker):
        """Calculates the current local database balance for a given asset
        by aggregating net transactional historical history.
        """
        query = """
            SELECT 
                SUM(CASE WHEN direction = 'INBOUND' THEN amount ELSE 0 END) as inbound_sum,
                SUM(CASE WHEN direction = 'OUTBOUND' THEN amount ELSE 0 END) as outbound_sum,
                SUM(CASE WHEN direction = 'OUTBOUND' THEN fee ELSE 0 END) as fee_sum
            FROM cold_wallet_history
            WHERE coin = ?
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, (coin_ticker.upper(),))
            row = cursor.fetchone()
            cursor.close()

            if row and (row[0] is not None or row[1] is not None):
                inbound = row[0] or 0.0
                outbound = row[1] or 0.0
                
                return inbound - outbound
            
            return 0.0
        except Exception as e:
            print(f"⚠️ Local ledger database calculation error for {coin_ticker}: {e}")
            return 0.0
    
    def get_cached_ticker(self, identifier: str) -> str:
        """Retrieves a locally mapped ticker string to prevent unnecessary web lookups."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT resolved_ticker FROM asset_ticker_map WHERE identifier = ?", (identifier,))
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None

    def save_ticker_mapping(self, identifier: str, resolved_ticker: str):
        """Permanently saves an identifier translation vector to the database vault."""
        self.conn.execute("""
            INSERT OR IGNORE INTO asset_ticker_map (identifier, resolved_ticker) 
            VALUES (?, ?)
        """, (identifier, resolved_ticker))
        self.conn.commit()

    