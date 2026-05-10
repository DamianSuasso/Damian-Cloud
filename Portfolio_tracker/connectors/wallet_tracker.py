import os
import requests
from dotenv import load_dotenv

load_dotenv()

class WalletTracker:
    def __init__(self):
        self.addresses = {
            'BTC': os.getenv("WALLET_BTC"),
            'ETH': os.getenv("WALLET_ETH"),
            'XRP': os.getenv("WALLET_XRP"),
            'LTC': os.getenv("WALLET_LTC"),
            # Add others here
        }

    def _fetch_balance(self, chain, url, json_path):
        """Helper to handle requests and errors across all chains"""
        addr = self.addresses.get(chain)
        if not addr:
            return "MISSING_ADDRESS"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            # Navigate the JSON path to get the value
            val = data
            for key in json_path:
                val = val.get(key, {})
            
            if isinstance(val, (int, float)):
                return val
            return f"ERROR: Unexpected API Response"
        except Exception as e:
            return f"CONNECTION_ERROR: {str(e)}"
        
    def get_btc_balance(self):
        addr = self.addresses.get('BTC')
        if not addr: return 0
        val = self._fetch_balance(
            'BTC', 
            f"https://api.blockchair.com/bitcoin/dashboards/address/{addr}", 
            ['final_balance']
        )
        return val / 100_000_000 if isinstance(val, (int, float)) else val

    def get_eth_balance(self):
        addr = self.addresses.get('ETH')
        if not addr: return 0
        val = self._fetch_balance(
            'ETH', 
            f"https://api.blockcypher.com/v1/eth/main/addrs/{addr}/balance", 
            ['final_balance']
        )
        
        return val /10**18 if isinstance(val, (int,float)) else val

    def get_xrp_balance(self):
        addr = self.addresses.get('XRP')
        if not addr: return 0
        val = self._fetch_balance(
            'XRP', 
            f"https://api.blockcypher.com/v1/xrp/main/addrs/{addr}/balance", 
            ['final_balance']
        )
        
        return val /10**18 if isinstance(val, (int,float)) else val

    def get_all_balances(self):
        """Orchestrates all checks"""
        balances = {}
        balances['BTC'] = self.get_btc_balance()
        balances['ETH'] = self.get_eth_balance()
        balances['XRP'] = self.get_xrp_balance()
        # We will add the other 8 chains in the next iteration
        return balances

if __name__ == "__main__":
    tracker = WalletTracker()
    print("Cold Wallet Balances:", tracker.get_all_balances())