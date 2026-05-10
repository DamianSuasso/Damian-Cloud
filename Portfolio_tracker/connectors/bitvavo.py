import os
from dotenv import load_dotenv
from python_bitvavo_api.bitvavo import Bitvavo

load_dotenv()

class BitvavoConnector:
    def __init__(self, mock=False):
        self.api_key = os.getenv("BITVAVO_KEY")
        self.api_secret = os.getenv("BITVAVO_SECRET")
        
        if mock or not self.api_key:
            self.is_mock = True
        else:
            self.is_mock = False
            # We add ACCESSWINDOW here to fix the 304 error
            self.client = Bitvavo({
                'APIKEY': self.api_key,
                'APISECRET': self.api_secret,
                'RESTURL': 'https://api.bitvavo.com/v2',
                'ACCESSWINDOW': 60000 
            })

    def get_balance(self):
        if self.is_mock:
            return [{'symbol': 'BTC', 'available': '0.05'}, {'symbol': 'ETH', 'available': '1.2'}]
        
        try:
            result = self.client.balance({})
            # IMPORTANT: If the result is a dictionary with an 'error', return empty list
            if isinstance(result, dict) and 'error' in result:
                print(f"❌ Bitvavo Error: {result['error']}")
                return []
            return result
        except Exception as e:
            print(f"❌ Bitvavo Connection Failed: {e}")
            return []