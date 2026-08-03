import os
from python_bitvavo_api.bitvavo import Bitvavo
from dotenv import load_dotenv

# Force load_dotenv to look in the current working directory absolute path
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))

class BitvavoConnector:
    api_key = os.getenv("BITVAVO_KEY")
    api_secret = os.getenv("BITVAVO_SECRET")
    bitvavo_engine = None

    def __init__(self, is_mock=False):
        self.is_mock = is_mock
        if not self.is_mock:
            if not self.api_key or not self.api_secret:
                raise ValueError("❌ Error: BITVAVO_APIKEY or BITVAVO_APISECRET missing from environment config!")

            self.bitvavo_engine = Bitvavo({
                'APIKEY': self.api_key,
                'APISECRET': self.api_secret
            })

    def get_balance(self):
        if self.is_mock:
            return [{'symbol': 'BTC', 'available': '0.05'}, {'symbol': 'ETH', 'available': '1.2'}]
        
        try:
            result = self.bitvavo_engine.balance({})
            if isinstance(result, dict) and 'error' in result:
                print(f"❌ Bitvavo Error {result['errorCode']}: {result['error']}")
                return []
            return result
        except Exception as e:
            print(f"❌ Bitvavo Connection Failed: {e}")
            return []

    def get_transaction_history(self, from_date = "0"):
        if self.is_mock:
            return [
                {
                    'transactionId': 'tx_mock_001',
                    'executedAt': '2026-01-15T12:00:00.000Z',
                    'type': 'buy',
                    'priceCurrency': 'EUR',
                    'priceAmount': '1500.00',
                    'sentCurrency': 'EUR',
                    'sentAmount': '1500.00',
                    'receivedCurrency': 'BTC',
                    'receivedAmount': '0.025',
                    'feesCurrency': 'EUR',
                    'feesAmount': '3.75'
                }
            ]

        try:
            all_transactions = []
            page = 1
            max_items_per_page = 100

            while True:
                options = {
                    'page': str(page),
                    'maxItems': str(max_items_per_page),
                    'fromDate': from_date
                }
                
                result = self.bitvavo_engine.privateRequest('/account/history', '', options, 'GET')
                
                if isinstance(result, dict) and 'error' in result:
                    print(f"❌ Bitvavo Error {result['errorCode']}: {result['error']}")
                    break
                
                # Check if the expected envelope structure exists
                if not isinstance(result, dict) or 'items' not in result:
                    print("❌ Unexpected data structure received from Bitvavo.")
                    break
                
                # Extract the actual list of transactions
                batch = result['items']
                # print("\n".join([f"🚨 REVEAL ADA: ID: {tx.get('transactionId') or tx.get('id')} | Type: {tx.get('type')} | Sent: {tx.get('sentAmount')} {tx.get('sentCurrency')} | Recv: {tx.get('receivedAmount')} {tx.get('receivedCurrency')}" for tx in batch if 'ADA' in str(tx)]))
                all_transactions.extend(batch)
                
                total_pages = result.get('totalPages', 1)
                print(f"📥 Processed page {page} of {total_pages}...")

                # Break loop if we've processed the final page or have no more items
                if page >= total_pages or len(batch) == 0:
                    break
                    
                page += 1
            
            print(f"✅ Successfully extracted {len(all_transactions)} total transactions.")
            return all_transactions

        except Exception as e:
            print(f"❌ Bitvavo History Sync Failed: {e}")
            return []