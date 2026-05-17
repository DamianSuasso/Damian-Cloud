import sqlite3

class DatabaseManager:
    def __init__(self, db_name="sentinel_vault.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        # Added fiat_currency column to handle USD, USDC, USDT, and EUR variations flawlessly
        query = """
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
        self.conn.execute(query)
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
                fiat_currency = tx.get('sentCurrency') # The cash/stablecoin you spent
            elif tx_type == 'sell':
                asset = tx.get('sentCurrency')
                amount = tx.get('sentAmount')
                fiat_value = tx.get('receivedAmount')
                fiat_currency = tx.get('receivedCurrency') # The cash/stablecoin you received
            elif tx_type in ['staking', 'distribution']:
                asset = tx.get('receivedCurrency')
                amount = tx.get('receivedAmount')
                fiat_value = 0.0
                fiat_currency = 'EUR' # Default baseline for rewards
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