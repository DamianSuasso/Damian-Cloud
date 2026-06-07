import os
import requests
from dotenv import load_dotenv

load_dotenv()

class WalletTracker:
    def __init__(self):
        # 1. Centralized Registry of Public APIs
        # format: 'COIN': (API_URL, JSON_PATH, DIVISOR)
        self.registry = {
            'BTC': (f"https://api.blockchair.com/bitcoin/dashboards/address/{os.getenv('WALLET_BTC')}", ['data', os.getenv('WALLET_BTC'), 'address', 'balance'], 100_000_000),
            'ETH': (f"https://api.blockcypher.com/v1/eth/main/addrs/{os.getenv('WALLET_ETH')}/balance", ['balance'], 10**18),
            #'LTC': (f"https://api.blockcypher.com/v1/ltc/main/addrs/{os.getenv('WALLET_LTC')}/balance", ['balance'], 10**8),
            'XRP': (f"https://data.ripple.com/v2/accounts/{os.getenv('WALLET_XRP')}/balances", ['balances'], 1), # XRP needs custom logic for list
            #'SOL': ("https://api.mainnet-beta.solana.com", [], 10**9), # SOL uses POST JSON-RPC
            #'ADA': (f"https://api.blockchair.com/cardano/dashboards/address/{os.getenv('WALLET_ADA')}", ['data', os.getenv('WALLET_ADA'), 'address', 'balance'], 1000_000)
        }

    def _get_json_value(self, data, path):
        """Helper to navigate complex JSON structures"""
        for key in path:
            if isinstance(data, dict):
                data = data.get(key, {})
            else:
                return 0
        return data

    def fetch_generic(self, coin):
        """Handles most standard REST APIs"""
        url, path, divisor = self.registry.get(coin, (None, None, None))
        if not url or "None" in url: return 0.0
        
        try:
            res = requests.get(url, timeout=10)
            data = res.json()

            # Check for Blockchair-specific error codes
            if res.status_code == 430:
                return f"RATE_LIMIT: {data.get('context', {}).get('error', 'Too many requests')}"
            
            if res.status_code != 200:
                return f"API_ERROR_{res.status_code}"
            
            raw_val = self._get_json_value(data, path)
            if isinstance(raw_val, (int, float)):
                return float(raw_val) / divisor
            
            return "DATA_FORMAT_ERROR"
        except Exception as e:
            print(f"⚠️ {coin} Fetch Error: {e}")
            return f"CONN_ERROR: {str(e)}"

    def fetch_solana(self):
        """Special case: Solana uses JSON-RPC (POST)"""
        addr = os.getenv('WALLET_SOL')
        if not addr: return 0.0
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [addr]}
            res = requests.post(self.registry['SOL'][0], json=payload).json()
            return res['result']['value'] / 10**9
        except:
            return 0.0

    def fetch_xrp(self):
        addr = os.getenv('WALLET_XRP')
        if not addr: return "MISSING_ADDRESS"
        
        # XRPL nodes use JSON-RPC POST requests
        payload = {
            "method": "account_info",
            "params": [{"account": addr, "ledger_index": "validated"}]
        }
        try:
            res = requests.post("https://xrplcluster.com", json=payload).json()
            # XRPL returns balance in "Drops" (1 XRP = 1,000,000 Drops)
            raw_balance = res['result']['account_data']['Balance']
            return float(raw_balance) / 1_000_000
        except KeyError:
            return "ERROR: Account Not Found"
        except Exception as e:
            return "CONN_ERROR"
        # url = self.registry.get('XRP', (None, None, None))[0]
        # if not url or "None" in url: return "MISSING_ADDRESS"
        
        # try:
        #     response = requests.get(url, timeout=10)
            
        #     # 1. Catch Authentication or Rate Limit errors
        #     if response.status_code == 401 or response.status_code == 403:
        #         return "AUTH_ERROR: Token Required"
        #     if response.status_code != 200:
        #         return f"API_ERROR: {response.status_code}"

        #     data = response.json()
            
        #     # 2. Extract balance logic
        #     balances = data.get('balances', [])
        #     for b in balances:
        #         if b.get('currency') == 'XRP':
        #             return float(b['value'])
            
        #     return 0.0 # Account exists but has 0 XRP
        # except Exception as e:
        #     return f"CONN_ERROR"
        
    def get_all_balances(self):
        """The Master Loop: Professionally clean"""
        results = {}
        for coin in self.registry.keys():
            if coin == 'SOL':
                results[coin] = self.fetch_solana()
            elif coin == 'XRP':
                results[coin] = self.fetch_xrp()
            else:
                results[coin] = self.fetch_generic(coin)
        return results

if __name__ == "__main__":
    tracker = WalletTracker()
    print("Cold Wallet Balances:", tracker.get_all_balances())