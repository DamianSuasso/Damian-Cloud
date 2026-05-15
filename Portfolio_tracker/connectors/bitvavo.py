import os
from dotenv import load_dotenv
from python_bitvavo_api.bitvavo import Bitvavo
import json
import time

load_dotenv()

class BitvavoConnector:
    api_key = os.getenv("BITVAVO_KEY")
    api_secret = os.getenv("BITVAVO_SECRET")
    bitvavo_engine = None
    bitvavo_socket = None

    def __init__(self, mock=False):   
        if mock or not self.api_key:
            self.is_mock = True
        else:
            self.is_mock = False
            self.bitvavo_engine = Bitvavo({
            'APIKEY': self.api_key,
            'APISECRET': self.api_secret
        })
        self.bitvavo_socket = self.bitvavo_engine.newWebsocket()
           
   
    def get_balance(self):
        if self.is_mock:
            return [{'symbol': 'BTC', 'available': '0.05'}, {'symbol': 'ETH', 'available': '1.2'}]
        
        try:
            result = self.bitvavo_engine.balance({})
            # IMPORTANT: If the result is a dictionary with an 'error', return empty list
            if isinstance(result, dict) and 'error' in result:
                print(f"❌ Bitvavo Error {result['errorCode']}: {result['error']}")
                return []
            return result
        except Exception as e:
            print(f"❌ Bitvavo Connection Failed: {e}")
            return []