import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from Portfolio_tracker.utils.db_manager import DatabaseManager

# Force explicitly searching from the current working directory path context
load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))

def sync_bitcoin_history():
    raw_address = os.getenv('WALLET_BTC')
    
    if not raw_address or raw_address.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] Error: WALLET_BTC environment variable is completely empty or missing.")
        return 0.0

    btc_address = raw_address.strip()
    print(f"🛰️ [SyncColdWallets] Target Address Confirmed: {btc_address}")
    
    # 1. First fetch the account statistics to extract the true live balance snapshot
    balance_url = f"https://mempool.space/api/address/{btc_address}"
    live_btc_balance = 0.0
    
    try:
        bal_res = requests.get(balance_url, timeout=10)
        if bal_res.status_code == 200:
            bal_data = bal_res.json()
            chain_stats = bal_data.get('chain_stats', {})
            # Live Satoshis = Total Funded - Total Spent
            live_sats = chain_stats.get('funded_txo_sum', 0) - chain_stats.get('spent_txo_sum', 0)
            live_btc_balance = float(live_sats) / 100_000_000
            print(f"💰 [SyncColdWallets] True On-Chain Controlled Balance: {live_btc_balance:.8f} BTC")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Balance checkpoint error fetching live BTC status: {e}")

    # 2. Fetch transaction histories
    tx_url = f"https://mempool.space/api/address/{btc_address}/txs"
    
    try:
        res = requests.get(tx_url, timeout=10)
        
        if res.status_code == 400:
            print(f"❌ [SyncColdWallets] API Status 400: Bad Request. Check that this is a valid Mainnet BTC address string.")
            print(f"❌ [SyncColdWallets] Attempted URL target was: {tx_url}")
            return live_btc_balance
        elif res.status_code != 200:
            print(f"❌ [SyncColdWallets] Failed to fetch BTC history. API status: {res.status_code}")
            return live_btc_balance
            
        raw_txs = res.json()
        parsed_entries = []

        for tx in raw_txs:
            tx_hash = tx.get('txid')
            status = tx.get('status', {})
            block_time = status.get('block_time')
            block_height = status.get('block_height', 0)
            
            if block_time:
                timestamp = datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()

            my_input_sum = 0
            my_output_sum = 0
            
            for vin in tx.get('vin', []):
                prevout = vin.get('prevout', {}) if vin.get('prevout') is not None else {}
                if prevout.get('scriptpubkey_address') == btc_address:
                    my_input_sum += prevout.get('value', 0)

            for vout in tx.get('vout', []):
                if vout.get('scriptpubkey_address') == btc_address:
                    my_output_sum += vout.get('value', 0)

            # Extract absolute transaction fee context
            network_fee_sats = tx.get('fee', 0)
            network_fee = float(network_fee_sats) / 100_000_000

            if my_input_sum > 0:
                direction = "OUTBOUND"
                # Gross drop in wallet value
                net_satoshis = my_input_sum - my_output_sum
                # Isolate the core amount sent away by pulling out the transaction fee
                if net_satoshis > network_fee_sats:
                    net_satoshis -= network_fee_sats
            else:
                direction = "INBOUND"
                net_satoshis = my_output_sum

            if net_satoshis <= 0:
                continue

            btc_amount = float(net_satoshis) / 100_000_000

            parsed_entries.append({
                'tx_hash': tx_hash,
                'timestamp': timestamp,
                'coin': 'BTC',
                'wallet_address': btc_address,
                'direction': direction,
                'amount': btc_amount,
                'fee': network_fee if direction == "OUTBOUND" else 0.0,
                'block_height': block_height
            })

        if parsed_entries:
            db = DatabaseManager()
            db.save_cold_wallet_transactions(parsed_entries)
            print(f"💾 Successfully processed and saved {len(parsed_entries)} BTC on-chain events to database.")
        else:
            print("✅ No matching ledger movements extracted for BTC address.")

    except Exception as e:
        print(f"❌ Bitcoin On-Chain Sync Error: {e}")

    # Return the live on-chain check value for main.py UI and audit loops
    return live_btc_balance

def sync_ethereum_history():
    raw_address = os.getenv('WALLET_ETH')
    if not raw_address or raw_address.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No WALLET_ETH found in your environment configuration. Skipping...")
        return 0.0

    # Normalize by converting to lowercase and completely stripping the '0x' prefix 
    # to guarantee clean matching with Blockcypher's address list strings.
    eth_address = raw_address.strip().lower().replace("0x", "")
    print(f"🛰️ [SyncColdWallets] Querying Blockcypher for Ethereum address history: {eth_address[:10]}...")
    
    url = f"https://api.blockcypher.com/v1/eth/main/addrs/0x{eth_address}/full"
    live_eth_balance = 0.0
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ [SyncColdWallets] Failed to fetch ETH history. API status: {res.status_code}")
            return live_eth_balance
            
        data = res.json()
        
        # Extract live verified account balance directly from Blockcypher (Value comes in Wei)
        live_wei = float(data.get('balance', 0))
        live_eth_balance = live_wei / 10**18
        print(f"💰 [SyncColdWallets] True On-Chain Controlled Balance: {live_eth_balance:.6f} ETH")

        raw_txs = data.get('txs', [])
        parsed_entries = []

        for tx in raw_txs:
            tx_hash = tx.get('hash')
            timestamp = tx.get('confirmed') or tx.get('received')
            block_height = tx.get('block_height', 0)

            # Extract network gas fees safely (Blockcypher feeds this in Wei)
            fees_wei = float(tx.get('fees', 0))
            fee_eth = fees_wei / 10**18

            my_input_volume = 0.0
            my_output_volume = 0.0
            is_input_owner = False

            # 1. Inspect Senders (Inputs)
            for inp in tx.get('inputs', []):
                for addr in inp.get('addresses', []):
                    clean_addr = str(addr).lower().replace("0x", "")
                    if clean_addr == eth_address:
                        my_input_volume += float(inp.get('value', 0))
                        is_input_owner = True

            # 2. Inspect Recipients (Outputs)
            for out in tx.get('outputs', []):
                for addr in out.get('addresses', []):
                    clean_addr = str(addr).lower().replace("0x", "")
                    if clean_addr == eth_address:
                        my_output_volume += float(out.get('value', 0))

            # 3. Determine flow direction and calculate values based on prefix-stripped match results
            if is_input_owner:
                direction = "OUTBOUND"
                # Pure output value check for standard transfers
                total_tx_val = float(tx.get('total', 0)) / 10**18
                amount_eth = total_tx_val if total_tx_val > 0 else 0.0
            else:
                direction = "INBOUND"
                amount_eth = my_output_volume / 10**18

            # Handle internal / complex transaction exceptions safely 
            # (e.g. your 2ef2a6ab... transaction where the contract transferred value directly to your outputs)
            if direction == "INBOUND" and amount_eth == 0:
                total_tx_val = float(tx.get('total', 0)) / 10**18
                if total_tx_val > 0:
                    amount_eth = total_tx_val

            parsed_entries.append({
                'tx_hash': tx_hash,
                'timestamp': timestamp,
                'coin': 'ETH',
                'wallet_address': f"0x{eth_address}",
                'direction': direction,
                'amount': amount_eth,
                'fee': fee_eth if direction == "OUTBOUND" else 0.0,
                'block_height': block_height
            })

        if parsed_entries:
            db = DatabaseManager()
            db.save_cold_wallet_transactions(parsed_entries)
            print(f"💾 [SyncColdWallets] Successfully processed and saved {len(parsed_entries)} ETH on-chain events via Blockcypher.")
        else:
            print("✅ [SyncColdWallets] No matching ledger movements extracted for ETH address.")

    except Exception as e:
        print(f"❌ [SyncColdWallets] Ethereum On-Chain Sync Error: {e}")

    # Return the live on-chain check value for main.py UI and audit loops
    return live_eth_balance

def sync_xrp_history():
    xrp_address = os.getenv('WALLET_XRP')
    if not xrp_address or xrp_address.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No WALLET_XRP found in your environment configuration. Skipping...")
        return 0.0

    xrp_address = xrp_address.strip()
    print(f"🛰️ [SyncColdWallets] Querying XRPL Cluster Node for XRP history: {xrp_address[:10]}...")
    
    url = "https://xrplcluster.com/"
    live_xrp_balance = 0.0

    # 1. First fetch the account info to get the definitive live on-chain balance
    info_payload = {
        "method": "account_info",
        "params": [
            {
                "account": xrp_address,
                "ledger_index": "validated"
            }
        ]
    }
    
    try:
        info_res = requests.post(url, json=info_payload, timeout=10)
        if info_res.status_code == 200:
            info_data = info_res.json()
            account_data = info_data.get('result', {}).get('account_data', {})
            # Balance field is natively returned in Drops
            raw_balance = account_data.get('Balance')
            if raw_balance is not None:
                live_xrp_balance = float(raw_balance) / 1_000_000
                print(f"💰 [SyncColdWallets] True On-Chain Controlled Balance: {live_xrp_balance:.6f} XRP")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Balance checkpoint error fetching live XRP status: {e}")

    # 2. Fetch transaction histories
    tx_payload = {
        "method": "account_tx",
        "params": [
            {
                "account": xrp_address,
                "ledger_index_min": -1,
                "ledger_index_max": -1,
                "limit": 50
            }
        ]
    }
    
    try:
        res = requests.post(url, json=tx_payload, timeout=10)
        if res.status_code != 200:
            print(f"❌ [SyncColdWallets] Failed to fetch XRP history. API status: {res.status_code}")
            return live_xrp_balance
            
        data = res.json()
        result = data.get('result', {})
        raw_txs = result.get('transactions', [])
        parsed_entries = []

        for tx_wrapper in raw_txs:
            tx = tx_wrapper.get('tx', {})
            
            if tx.get('TransactionType') != 'Payment':
                continue

            tx_hash = tx.get('hash')
            block_height = tx.get('ledger_index', 0)

            # Look for Ripple Epoch time field using an adaptive path fallback
            ripple_time = tx.get('date') or tx_wrapper.get('date')
            
            if ripple_time is not None and int(ripple_time) > 0:
                # 1 XRP Epoch second = 1 Unix second. Ripple Epoch starts Jan 1 2000 (946684800 Unix)
                unix_time = int(ripple_time) + 946684800
                timestamp = datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()

            sender = tx.get('Account')
            
            raw_amount = tx.get('Amount')
            if isinstance(raw_amount, dict):
                continue
            
            amount_xrp = float(raw_amount) / 1_000_000
            fee_xrp = float(tx.get('Fee', 0)) / 1_000_000

            if sender == xrp_address:
                direction = "OUTBOUND"
                execution_amount = amount_xrp
            else:
                direction = "INBOUND"
                execution_amount = amount_xrp

            parsed_entries.append({
                'tx_hash': tx_hash,
                'timestamp': timestamp,
                'coin': 'XRP',
                'wallet_address': xrp_address,
                'direction': direction,
                'amount': execution_amount,
                'fee': fee_xrp if direction == "OUTBOUND" else 0.0,
                'block_height': block_height
            })

        if parsed_entries:
            db = DatabaseManager()
            db.save_cold_wallet_transactions(parsed_entries)
            print(f"💾 [SyncColdWallets] Successfully processed and saved {len(parsed_entries)} XRP on-chain events via XRPL Node.")
        else:
            print("✅ [SyncColdWallets] No matching ledger movements extracted for XRP address.")

    except Exception as e:
        print(f"❌ [SyncColdWallets] XRP On-Chain Sync Error: {e}")

    # Return the live balance back out to the matrix orchestrator
    return live_xrp_balance

def sync_bsc_history_BSCCHAINAPI_REQUIRED():
    raw_address = os.getenv('WALLET_ETH')
    etherscan_key = os.getenv('ETHERSCAN_API_KEY')
    
    # Validation checks point to the unified key asset variable now
    if not raw_address or raw_address.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No WALLET_ETH address found in environment variables. Skipping...")
        return
    if not etherscan_key or etherscan_key.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No ETHERSCAN_API_KEY found in your environment. Skipping BSC sync...")
        return

    bsc_address = raw_address.strip().lower()
    clean_key = etherscan_key.strip().replace('"', '').replace("'", "")
    
    print(f"🛰️ [SyncColdWallets] Querying Unified Etherscan API V2 for BSC (Chain 56) asset history...")

    parsed_entries = {}
    
    # Etherscan V2 infrastructure routing link specialized for the BSC ledger network
    v2_bsc_endpoint = "https://api.etherscan.io/v2/api"

    # ==============================================================================
    # 1. FETCH NATIVE BNB TRANSACTIONS
    # ==============================================================================
    bnb_url = f"{v2_bsc_endpoint}?chainid=56&module=account&action=txlist&address={bsc_address}&startblock=0&endblock=99999999&sort=desc&apikey={clean_key}"
    
    try:
        res = requests.get(bnb_url, timeout=10)
        if res.status_code == 200:
            res_data = res.json()
            status = res_data.get("status")
            message = res_data.get("message", "")
            
            if status == "1":
                for tx in res_data.get("result", []):
                    tx_hash = tx.get("hash")
                    timestamp = datetime.fromtimestamp(int(tx.get("timeStamp")), tz=timezone.utc).isoformat()
                    from_addr = tx.get("from", "").lower()
                    
                    value_bnb = float(tx.get("value", 0)) / 10**18
                    fee_bnb = (float(tx.get("gasUsed", 0)) * float(tx.get("gasPrice", 0))) / 10**18
                    
                    direction = "OUTBOUND" if from_addr == bsc_address else "INBOUND"
                    
                    if value_bnb == 0 and direction == "INBOUND":
                        continue

                    parsed_entries[tx_hash] = {
                        'tx_hash': tx_hash,
                        'timestamp': timestamp,
                        'coin': 'BNB',
                        'wallet_address': f"0x{bsc_address.replace('0x', '')}",
                        'direction': direction,
                        'amount': value_bnb,
                        'fee': fee_bnb if direction == "OUTBOUND" else 0.0,
                        'block_height': int(tx.get("blockNumber", 0))
                    }
            elif "No transactions found" in message or status == "0":
                print("ℹ️ [SyncColdWallets] Etherscan V2 Info: No native BNB movements found.")
            else:
                print(f"⚠️ [SyncColdWallets] Etherscan V2 Warning (BNB): {message}")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Error fetching native BNB layout via V2: {e}")

    # ==============================================================================
    # 2. FETCH BEP-20 TOKEN TRANSACTIONS (USDT, CAKE, LINK, etc.)
    # ==============================================================================
    token_url = f"{v2_bsc_endpoint}?chainid=56&module=account&action=tokentx&address={bsc_address}&startblock=0&endblock=99999999&sort=desc&apikey={clean_key}"
    
    try:
        res = requests.get(token_url, timeout=10)
        if res.status_code == 200:
            res_data = res.json()
            status = res_data.get("status")
            message = res_data.get("message", "")
            
            if status == "1":
                for tx in res_data.get("result", []):
                    tx_hash = tx.get("hash")
                    timestamp = datetime.fromtimestamp(int(tx.get("timeStamp")), tz=timezone.utc).isoformat()
                    from_addr = tx.get("from", "").lower()
                    
                    asset_ticker = tx.get("tokenSymbol", "UNKNOWN").upper()
                    decimals = int(tx.get("tokenDecimal", 18))
                    value_token = float(tx.get("value", 0)) / (10 ** decimals)
                    
                    direction = "OUTBOUND" if from_addr == bsc_address else "INBOUND"
                    existing_fee = parsed_entries.get(tx_hash, {}).get('fee', 0.0)
                    
                    parsed_entries[tx_hash] = {
                        'tx_hash': tx_hash,
                        'timestamp': timestamp,
                        'coin': asset_ticker,
                        'wallet_address': f"0x{bsc_address.replace('0x', '')}",
                        'direction': direction,
                        'amount': value_token,
                        'fee': existing_fee,
                        'block_height': int(tx.get("blockNumber", 0))
                    }
            elif "No transactions found" in message or status == "0":
                print("ℹ️ [SyncColdWallets] Etherscan V2 Info: No BEP-20 token movements found.")
            else:
                print(f"⚠️ [SyncColdWallets] Etherscan V2 Warning (Token): {message}")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Error fetching BEP-20 token layout via V2: {e}")

    # ==============================================================================
    # 3. SAVE MERGED LOG ENTRIES TO THE DATABASE
    # ==============================================================================
    final_list = list(parsed_entries.values())
    if final_list:
        db = DatabaseManager()
        db.save_cold_wallet_transactions(final_list)
        print(f"💾 [SyncColdWallets] Successfully cached {len(final_list)} BSC ecosystem events via Etherscan V2.")
    else:
        print("✅ [SyncColdWallets] No valid ledger movements found across BNB or BEP-20 lists.")

def sync_bsc_history():
    raw_address = os.getenv('WALLET_ETH')
    ankr_url = os.getenv('ANKR_BSC_URL')
    
    if not raw_address or raw_address.strip() in ["", "None"]:
        print("🛑 [SyncColdWallets] No WALLET_ETH address found in environment variables. Skipping...")
        return {}
    if not ankr_url or ankr_url.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No ANKR_BSC_URL found in your environment. Skipping BSC sync...")
        return {}

    bsc_address = raw_address.strip().lower()
    print(f"🛰️ [SyncColdWallets] Directly querying Ankr Indexer by wallet address for complete BSC history...")
    
    headers = {"Content-Type": "application/json"}
    live_bsc_balances = {}

    # 1. Fetch live account balances across all BEP-20 assets from Ankr
    balance_payload = {
        "jsonrpc": "2.0",
        "method": "ankr_getAccountBalance",
        "id": 1,
        "params": {
            "walletAddress": bsc_address,
            "blockchain": "bsc"
        }
    }
    
    try:
        bal_res = requests.post(ankr_url, json=balance_payload, headers=headers, timeout=10)
        if bal_res.status_code == 200:
            assets = bal_res.json().get('result', {}).get('assets', [])
            for asset in assets:
                symbol = asset.get('tokenSymbol', '').upper()
                balance_val = float(asset.get('balance', 0))
                if balance_val > 0:
                    live_bsc_balances[symbol] = balance_val
            
            # Print a neat summary of what was found on-chain
            balance_str = ", ".join([f"{v:.4f} {k}" for k, v in live_bsc_balances.items()])
            print(f"💰 [SyncColdWallets] True On-Chain Controlled Balances: {balance_str if balance_str else '0.00 BNB'}")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Balance checkpoint error fetching live BSC assets: {e}")

    # Fallback to ensure BNB key exists even if balance is absolute zero
    if "BNB" not in live_bsc_balances:
        live_bsc_balances["BNB"] = 0.0

    # 2. Fetch transaction histories
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "ankr_getTransactionsByAddress",
        "params": {
            "address": bsc_address,
            "blockchain": "bsc",
            "pageSize": 100
        }
    }
    
    try:
        res = requests.post(ankr_url, json=payload, headers=headers, timeout=15)
        data = res.json()
        
        if "error" in data:
            print(f"❌ [SyncColdWallets] Ankr Server Error: {data['error'].get('message')} (Code: {data['error'].get('code')})")
            return live_bsc_balances
            
        tx_wrapper = data.get('result', {})
        raw_txs = tx_wrapper.get('transactions', [])
        
        parsed_entries = []
        TOKEN_CONTRACTS = {
            "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": "WBNB",
            "0xe9e7cea3dedca5984780bafc599bd69add087d56": "BUSD",
            "0x55d398326f99059ff775485246999027b3197955": "USDT",
            "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82": "CAKE"
        }
        TARGET_COINS = ["BNB", "WBNB", "USDT", "BUSD", "CAKE", "HELLO", "LINK"]

        for tx in raw_txs:
            tx_hash = tx.get('hash') or tx.get('transactionHash')
            from_addr = str(tx.get('from', '')).lower()
            
            # --- Decode metadata base fields ---
            raw_block = tx.get('blockNumber', '0x0')
            block_height = int(raw_block, 16) if isinstance(raw_block, str) and raw_block.startswith('0x') else int(raw_block or 0)
            
            raw_time = tx.get('timestamp', '0x0')
            if isinstance(raw_time, str) and raw_time.startswith('0x'):
                unix_ts = int(raw_time, 16)
                timestamp = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()

            raw_gas = tx.get('gasUsed', '0x0')
            raw_price = tx.get('gasPrice', '0x0')
            gas_used = int(raw_gas, 16) if str(raw_gas).startswith('0x') else int(raw_gas or 0)
            gas_price = int(raw_price, 16) if str(raw_price).startswith('0x') else int(raw_price or 0)
            fee_bnb = (gas_used * gas_price) / 10**18

            # --- Evaluate native BNB transfers ---
            raw_val = tx.get('value', '0x0')
            value_wei = int(raw_val, 16) if str(raw_val).startswith('0x') else int(raw_val or 0)
            
            if value_wei > 0:
                amount_bnb = value_wei / 10**18
                direction = "OUTBOUND" if from_addr == bsc_address else "INBOUND"
                
                parsed_entries.append({
                    'tx_hash': tx_hash,
                    'timestamp': timestamp,
                    'coin': 'BNB',
                    'wallet_address': bsc_address,
                    'direction': direction,
                    'amount': amount_bnb,
                    'fee': fee_bnb if direction == "OUTBOUND" else 0.0,
                    'block_height': block_height
                })

            # --- Evaluate internal BEP-20 token transfers ---
            logs = tx.get('logs', []) or []
            for log in logs:
                event_data = log.get('event') or {}
                if event_data.get('name') != "Transfer":
                    continue
                
                contract_address = str(log.get('address', '')).lower()
                ticker = TOKEN_CONTRACTS.get(contract_address, "UNKNOWN")
                
                inputs = event_data.get('inputs', [])
                log_from = ""
                log_to = ""
                raw_decoded_value = "0"

                for inp in inputs:
                    name = inp.get('name')
                    if name == "_from":
                        log_from = str(inp.get('valueDecoded', '')).lower()
                    elif name == "_to":
                        log_to = str(inp.get('valueDecoded', '')).lower()
                    elif name == "_value":
                        raw_decoded_value = str(inp.get('valueDecoded', '0'))

                if bsc_address not in [log_from, log_to]:
                    continue

                if ticker == "UNKNOWN":
                    ticker = contract_address[:8].upper() 

                if ticker not in TARGET_COINS:
                    continue

                amount_token = float(raw_decoded_value) / 10**18
                if amount_token == 0:
                    continue

                log_direction = "OUTBOUND" if log_from == bsc_address else "INBOUND"

                parsed_entries.append({
                    'tx_hash': tx_hash,
                    'timestamp': timestamp,
                    'coin': ticker,
                    'wallet_address': bsc_address,
                    'direction': log_direction,
                    'amount': amount_token,
                    'fee': fee_bnb if log_direction == "OUTBOUND" and from_addr == bsc_address else 0.0,
                    'block_height': block_height
                })

        if parsed_entries:
            unique_map = {}
            for entry in parsed_entries:
                key = f"{entry['tx_hash']}_{entry['coin']}_{entry['direction']}_{entry['amount']}"
                unique_map[key] = entry

            db = DatabaseManager()
            db.save_cold_wallet_transactions(list(unique_map.values()))
            print(f"💾 [SyncColdWallets] Successfully indexed {len(unique_map)} clean base-10 BSC ledger events.")
        else:
            print("✅ [SyncColdWallets] BSC evaluation clear: No matching asset actions found.")

    except Exception as e:
        print(f"❌ [SyncColdWallets] Ankr Hex Processing Engine Error: {e}")

    # Return the dictionary of all live on-chain token assets
    return live_bsc_balances

# def sync_ada_history_OLD():
    raw_stake_address = os.getenv('WALLET_ADA')
    blockfrost_key = os.getenv('BLOCKFROST_API_KEY')
    
    if not raw_stake_address or raw_stake_address.strip() in ["", "None"]:
        print("🛑 [SyncColdWallets] No WALLET_ADA stake key found in environment variables. Skipping...")
        return
    if not blockfrost_key or blockfrost_key.strip() in ["", "None"]:
        print("🛑 [SyncColdWallets] No BLOCKFROST_API_KEY found in your environment. Skipping ADA sync...")
        return

    stake_address = raw_stake_address.strip()
    headers = {"project_id": blockfrost_key.strip()}
    
    # Validation: Ensure the user provided a stake key rather than a regular address
    if not stake_address.startswith("stake"):
        print("⚠️ [SyncColdWallets] Warning: WALLET_ADA should be your 'stake1...' key to track multiple addresses.")
        return

    print(f"🛰️ [SyncColdWallets] Querying Blockfrost Indexer for all active addresses linked to Stake Key...")
    
    # Step 1: Discover all distinct addresses belonging to this wallet account footprint
    discovery_url = f"https://cardano-mainnet.blockfrost.io/api/v0/accounts/{stake_address}/addresses"
    
    try:
        discovery_res = requests.get(discovery_url, headers=headers, timeout=10)
        if discovery_res.status_code == 404:
            print("ℹ️ [SyncColdWallets] Blockfrost Info: No active addresses mapped to this stake profile.")
            return
        elif discovery_res.status_code != 200:
            print(f"❌ [SyncColdWallets] Failed account address map discovery. Status: {discovery_res.status_code}")
            return
            
        discovered_addresses = [item.get("address") for item in discovery_res.json() if item.get("address")]
        print(f"🎯 [SyncColdWallets] Discovered {len(discovered_addresses)} active sub-address paths for this wallet.")
        
        parsed_entries = []

        # Step 2: Extract transactions for each discovered sub-address path cleanly
        for idx, addr in enumerate(discovered_addresses, 1):
            print(f" └─ Checking path [{idx}/{len(discovered_addresses)}]: {addr[:12]}...")
            
            tx_url = f"https://cardano-mainnet.blockfrost.io/api/v0/addresses/{addr}/transactions"
            res = requests.get(tx_url, headers=headers, params={"sort": "desc", "count": 50}, timeout=10)
            
            if res.status_code != 200:
                continue
                
            raw_txs = res.json()

            for tx in raw_txs:
                tx_hash = tx.get("tx_hash")
                block_height = int(tx.get("block_height", 0))
                
                block_time = tx.get("block_time")
                timestamp = datetime.fromtimestamp(int(block_time), tz=timezone.utc).isoformat() if block_time else datetime.now(timezone.utc).isoformat()

                # Parse specific UTXO allocation states to find net impact on this specific address
                utxo_url = f"https://cardano-mainnet.blockfrost.io/api/v0/txs/{tx_hash}/utxos"
                utxo_res = requests.get(utxo_url, headers=headers, timeout=10)
                if utxo_res.status_code != 200:
                    continue
                    
                utxo_data = utxo_res.json()
                
                input_sum = sum(float(item.get("amount", [{}])[0].get("quantity", 0)) 
                                for item in utxo_data.get("inputs", []) if item.get("address") == addr)
                
                output_sum = sum(float(item.get("amount", [{}])[0].get("quantity", 0)) 
                                 for item in utxo_data.get("outputs", []) if item.get("address") == addr)
                
                net_lovelace = output_sum - input_sum
                if net_lovelace == 0:
                    continue # Skips internal wallet changes or gas optimizations

                direction = "INBOUND" if net_lovelace > 0 else "OUTBOUND"
                amount_ada = abs(net_lovelace) / 10**6
                
                fee_lovelace = float(utxo_data.get("fees", 0)) if direction == "OUTBOUND" else 0.0
                fee_ada = fee_lovelace / 10**6

                parsed_entries.append({
                    'tx_hash': tx_hash,
                    'timestamp': timestamp,
                    'coin': 'ADA',
                    'wallet_address': addr, # Saves the specific address that processed the volume
                    'direction': direction,
                    'amount': amount_ada,
                    'fee': fee_ada,
                    'block_height': block_height
                })

        if parsed_entries:
            # Dedup across addresses just in case an internal transaction hits multiple of your own addresses
            unique_entries = {e['tx_hash']: e for e in parsed_entries}.values()
            
            db = DatabaseManager()
            db.save_cold_wallet_transactions(list(unique_entries))
            print(f"💾 [SyncColdWallets] Success: Cached {len(unique_entries)} consolidated ADA account history events.")
        else:
            print("✅ [SyncColdWallets] Account scan complete: No active multi-address asset movements found.")

    except Exception as e:
        print(f"❌ [SyncColdWallets] Cardano Multi-Address Tracking Fault: {e}")

def sync_ada_history():
    raw_stake_address = os.getenv('WALLET_ADA')
    blockfrost_key = os.getenv('BLOCKFROST_API_KEY')
    
    if not raw_stake_address or raw_stake_address.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No WALLET_ADA stake key found in environment variables. Skipping...")
        return 0.0
    if not blockfrost_key or blockfrost_key.strip() in ["", "None"]:
        print("❌ [SyncColdWallets] No BLOCKFROST_API_KEY found in your environment. Skipping ADA sync...")
        return 0.0

    stake_address = raw_stake_address.strip()
    headers = {"project_id": blockfrost_key.strip()}
    
    if not stake_address.startswith("stake"):
        print("⚠️ [SyncColdWallets] Warning: WALLET_ADA must be your 'stake1...' key to reconcile multi-address balances.")
        return 0.0

    print(f"🛰️ [SyncColdWallets] Auditing true account balance metrics via Blockfrost...")
    account_url = f"https://cardano-mainnet.blockfrost.io/api/v0/accounts/{stake_address}"
    controlled_amount = 0.0
    
    try:
        acc_res = requests.get(account_url, headers=headers, timeout=10)
        if acc_res.status_code == 200:
            acc_data = acc_res.json()
            controlled_amount = float(acc_data.get('controlled_amount', 0)) / 10**6
            withdrawable_rewards = float(acc_data.get("withdrawable_amount", 0)) / 10**6
            print(f"💰 [SyncColdWallets] True Live Controlled Balance: {controlled_amount:.6f} ADA")
            print(f"🎁 [SyncColdWallets] Hidden Unwithdrawn Staking Rewards: {withdrawable_rewards:.6f} ADA")
    except Exception as e:
        print(f"⚠️ [SyncColdWallets] Live profile audit warning: {e}")

    # ==============================================================================
    # STEP 1: MAP THE WALLET FOOTPRINT
    # ==============================================================================
    discovery_url = f"https://cardano-mainnet.blockfrost.io/api/v0/accounts/{stake_address}/addresses"
    try:
        discovery_res = requests.get(discovery_url, headers=headers, timeout=10)
        if discovery_res.status_code != 200:
            print("❌ [SyncColdWallets] Failed to map account footprint addresses.")
            return controlled_amount
            
        my_wallet_addresses = {item.get("address") for item in discovery_res.json() if item.get("address")}
        print(f"🎯 [SyncColdWallets] Discovered {len(my_wallet_addresses)} active sub-address paths for this wallet.")
        
        all_tx_hashes = set()
        for idx, addr in enumerate(my_wallet_addresses, 1):
            print(f" └─ Checking path [{idx}/{len(my_wallet_addresses)}]: {addr[:12]}...")
            
            tx_url = f"https://cardano-mainnet.blockfrost.io/api/v0/addresses/{addr}/transactions"
            res = requests.get(tx_url, headers=headers, params={"sort": "desc", "count": 50}, timeout=10)
            if res.status_code == 200:
                for tx in res.json():
                    all_tx_hashes.add(tx.get("tx_hash"))

        print(f"📡 [SyncColdWallets] Evaluating {len(all_tx_hashes)} unique transaction contexts across the eUTXO space...")
        parsed_entries = []

        # ==============================================================================
        # STEP 2: RECONCILE THE BALANCE SHEETS (GLOBAL TRANSACTION SNAPSHOT)
        # ==============================================================================
        for tx_hash in all_tx_hashes:
            utxo_url = f"https://cardano-mainnet.blockfrost.io/api/v0/txs/{tx_hash}/utxos"
            utxo_res = requests.get(utxo_url, headers=headers, timeout=10)
            if utxo_res.status_code != 200:
                continue
            utxo_data = utxo_res.json()

            total_input_lovelace = sum(
                float(item.get("amount", [{}])[0].get("quantity", 0))
                for item in utxo_data.get("inputs", []) if item.get("address") in my_wallet_addresses
            )
            
            total_output_lovelace = sum(
                float(item.get("amount", [{}])[0].get("quantity", 0))
                for item in utxo_data.get("outputs", []) if item.get("address") in my_wallet_addresses
            )

            net_lovelace = total_output_lovelace - total_input_lovelace
            if net_lovelace == 0:
                continue

            direction = "INBOUND" if net_lovelace > 0 else "OUTBOUND"
            amount_ada = abs(net_lovelace) / 10**6

            details_url = f"https://cardano-mainnet.blockfrost.io/api/v0/txs/{tx_hash}"
            details_res = requests.get(details_url, headers=headers, timeout=10)
            
            if details_res.status_code == 200:
                tx_details = details_res.json()
                block_height = int(tx_details.get("block_height", 0))
                fee_lovelace = float(tx_details.get("fees", 0))
                fee_ada = fee_lovelace / 10**6 if direction == "OUTBOUND" else 0.0
                
                block_time = tx_details.get("block_time")
                if block_time:
                    timestamp = datetime.fromtimestamp(int(block_time), tz=timezone.utc).isoformat()
                else:
                    timestamp = datetime.now(timezone.utc).isoformat()
            else:
                block_height = int(utxo_data.get("block_height", 0)) if utxo_data.get("block_height") else 0
                fee_ada = 0.0
                timestamp = datetime.now(timezone.utc).isoformat()

            if direction == "OUTBOUND" and fee_ada > 0:
                amount_ada = max(0.0, amount_ada - fee_ada)

            parsed_entries.append({
                'tx_hash': tx_hash,
                'timestamp': timestamp,
                'coin': 'ADA',
                'wallet_address': list(my_wallet_addresses)[0],
                'direction': direction,
                'amount': amount_ada,
                'fee': fee_ada,
                'block_height': block_height
            })

        if parsed_entries:
            db = DatabaseManager()
            db.save_cold_wallet_transactions(parsed_entries)
            print(f"💾 [SyncColdWallets] Success: Saved {len(parsed_entries)} audited ADA records with precise block and fee tallies.")
        else:
            print("✅ [SyncColdWallets] Account analysis complete: All movements match expected baseline targets.")

    except Exception as e:
        print(f"❌ [SyncColdWallets] Cardano Global Accounting Engine Fault: {e}")

    # Definitive return vector for the view layer layout matrix
    return controlled_amount

def sync_all_wallets():
    """Master orchestrator function to sequentially sync all on-chain cold wallets."""
    print("🛰️ [SyncColdWallets] Starting complete cold wallet on-chain synchronization matrix...")
    balances = {}

    # --- 1. Execute BSC Sync & Audit ---
    try:
        bsc_balances = sync_bsc_history()
        db = DatabaseManager()
        
        for coin, live_val in bsc_balances.items():
            balances[coin] = live_val
            
            # Audit checking each active token balance
            db_calculated = db.get_calculated_balance_for_coin(coin)
            print(f"🔍 [SyncColdWallets] [{coin} Audit] On-Chain: {live_val:.4f} | Local DB Tally: {db_calculated:.4f}")
            
            if abs(live_val - db_calculated) > 0.01:
                print(f"⚠️ [SyncColdWallets] Fact-Check Alert: Local {coin} ledger delta detected! On-chain reality takes priority.")
    except Exception as e:
        print(f"❌ [SyncColdWallets] BSC Engine Sync/Audit Failure: {e}")
        balances["BNB"] = "Sync Error"
        
    # --- 2. Execute Cardano Sync & Audit ---
    try:
        live_ada = sync_ada_history()
        balances["ADA"] = live_ada
        
        db = DatabaseManager()
        db_calculated_ada = db.get_calculated_balance_for_coin("ADA") 
        
        print(f"🔍 [ADA Audit] On-Chain: {live_ada:.4f} | Local DB Tally: {db_calculated_ada:.4f}")
        if abs(live_ada - db_calculated_ada) > 0.01:
            print(f"⚠️ [SyncColdWallets] Fact-Check Alert: Local ADA ledger delta detected! On-chain reality takes priority.")
    except Exception as e:
        print(f"❌ [SyncColdWallets] ADA Engine Sync/Audit Failure: {e}")
        balances["ADA"] = "Sync Error"

    # --- 3. Execute Bitcoin Sync & Audit ---
    try:
        live_btc = sync_bitcoin_history()
        balances["BTC"] = live_btc
        
        db = DatabaseManager()
        db_calculated_btc = db.get_calculated_balance_for_coin("BTC")
        
        print(f"🔍 [SyncColdWallets] [BTC Audit] On-Chain: {live_btc:.8f} | Local DB Tally: {db_calculated_btc:.8f}")
        if abs(live_btc - db_calculated_btc) > 0.00001:
            print(f"⚠️ [SyncColdWallets] Fact-Check Alert: Local BTC ledger delta detected! On-chain reality takes priority.")
    except Exception as e:
        print(f"❌ [SyncColdWallets] Bitcoin Engine Sync/Audit Failure: {e}")
        balances["BTC"] = "Sync Error"

    # --- 4. Execute Ethereum Sync & Audit ---
    try:
        live_eth = sync_ethereum_history()
        balances["ETH"] = live_eth
        
        db = DatabaseManager()
        db_calculated_eth = db.get_calculated_balance_for_coin("ETH")
        
        print(f"🔍 [SyncColdWallets] [ETH Audit] On-Chain: {live_eth:.6f} | Local DB Tally: {db_calculated_eth:.6f}")
        if abs(live_eth - db_calculated_eth) > 0.0001:
            print(f"⚠️ [SyncColdWallets] Fact-Check Alert: Local ETH ledger delta detected! On-chain reality takes priority.")
    except Exception as e:
        print(f"❌ [SyncColdWallets] Ethereum Engine Sync/Audit Failure: {e}")
        balances["ETH"] = "Sync Error"

    # --- 5. Execute XRP Sync & Audit ---
    try:
        live_xrp = sync_xrp_history()
        balances["XRP"] = live_xrp
        
        db = DatabaseManager()
        db_calculated_xrp = db.get_calculated_balance_for_coin("XRP")
        
        print(f"🔍 [SyncColdWallets] [XRP Audit] On-Chain: {live_xrp:.4f} | Local DB Tally: {db_calculated_xrp:.4f}")
        if abs(live_xrp - db_calculated_xrp) > 0.01:
            print(f"⚠️ [SyncColdWallets] Fact-Check Alert: Local XRP ledger delta detected! On-chain reality takes priority.")
    except Exception as e:
        print(f"❌ [SyncColdWallets] XRP Engine Sync/Audit Failure: {e}")
        balances["XRP"] = "Sync Error"

    print("✨ [SyncColdWallets] ALL SYNC OPERATIONS EXECUTED CLEANLY")

    return balances

if __name__ == "__main__":
    sync_all_wallets()