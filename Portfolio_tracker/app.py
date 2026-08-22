import sys
import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Path Injection ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from Portfolio_tracker.connectors.bitvavo import BitvavoConnector
from Portfolio_tracker.utils.crypto_price_service import CryptoPriceService
from Portfolio_tracker.utils.stock_price_service import StockPriceService
from Portfolio_tracker.utils.analyzer import PortfolioAnalyzer
from Portfolio_tracker.agents.analyst import SentinelAnalyst
from Portfolio_tracker.utils.db_manager import DatabaseManager
from Portfolio_tracker.utils.financial_utils import calculate_cost_basis_summary, sync_all_portfolio_prices

from Portfolio_tracker.sync_crypto import sync_bitvavo
from Portfolio_tracker.sync_cold_wallets import sync_all_wallets
from Portfolio_tracker.sync_stocks import sync_stocks

@st.cache_data(ttl=600)
def fetch_timeline_data(_analyzer_instance):
    return _analyzer_instance.get_portfolio_historical_timeline()

# Page Configuration
st.set_page_config(page_title="Sentinel Portfolio Console", layout="wide", page_icon="🛡️")

# Custom CSS for UI polish
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ Sentinel Portfolio Console")
st.caption("Live Unified Dashboard: Crypto, Equities & Cold Storage")

# Initialize DB Manager
db_manager = DatabaseManager()

# --- CACHED HEAVY LOADERS ---
@st.cache_resource
def get_price_engines():
    crypto_service = CryptoPriceService(db_manager=db_manager)
    stock_service = StockPriceService(db_manager=db_manager)
    return crypto_service, stock_service

crypto_service, stock_service = get_price_engines()
analyzer = PortfolioAnalyzer(db_manager=db_manager)

# --- HELPER: FETCH ASSET SECTOR & TRANSACTIONS ---
def get_stock_sector_map():
    """Fetches mapped sectors for stock identifiers from asset_ticker_map."""
    sector_map = {}
    try:
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT identifier, sector FROM asset_ticker_map WHERE sector IS NOT NULL")
        rows = cursor.fetchall()
        for identifier, sector in rows:
            if identifier and sector:
                sector_map[identifier.upper()] = sector
        conn.close()
    except Exception as e:
        print(f"⚠️ [APP/MAIN] Sector lookup warning: {e}")
    return sector_map

def clean_symbol(sym):
    """Normalize asset tickers (e.g., 'BTC-EUR' -> 'BTC')."""
    if not sym:
        return ""
    sym = str(sym).strip().upper()
    for suffix in ["-EUR", "/EUR", "-USDT", "/USDT"]:
        if sym.endswith(suffix):
            sym = sym[:-len(suffix)]
            break
    return sym

def get_asset_cost_bases():
    """Reads transactions from bitvavo_history, cold_wallet_history, degiro_history,
    and trade_republic_history, formats them for calculate_cost_basis_summary,
    and returns cost basis summaries per asset.
    """
    asset_tx_map = {}

    def add_tx(asset_name, tx_type, amount, price_eur, price_usdt=0.0, fee_eur=0.0, fee_usdt=0.0):
        key = clean_symbol(asset_name)
        if not key or amount <= 0:
            return
        if key not in asset_tx_map:
            asset_tx_map[key] = []
            
        asset_tx_map[key].append({
            'type': tx_type.upper(),
            'amount': float(amount or 0.0),
            'price_eur': float(price_eur or 0.0),
            'price_usdt': float(price_usdt or 0.0),
            'fee_eur': float(fee_eur or 0.0),
            'fee_usdt': float(fee_usdt or 0.0)
        })

    try:
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        # 1. Parse Bitvavo Exchange History
        try:
            cursor.execute("""
                SELECT asset, type, amount, fiat_value, fiat_currency, fee, fee_currency 
                FROM bitvavo_history 
                ORDER BY timestamp ASC
            """)
            for asset, t_type, amount, fiat_val, fiat_curr, fee, fee_curr in cursor.fetchall():
                if not asset or asset.upper() == 'EUR':
                    continue
                
                raw_type = str(t_type or '').lower()
                amt = float(amount or 0.0)
                fiat = float(fiat_val or 0.0)
                fee_val = float(fee or 0.0)
                
                unit_price = (fiat / amt) if (amt > 0 and fiat > 0) else 0.0
                
                p_eur = unit_price if fiat_curr == 'EUR' else 0.0
                p_usdt = unit_price if fiat_curr in ['USDT', 'USDC'] else 0.0
                f_eur = fee_val if fee_curr == 'EUR' else 0.0
                f_usdt = fee_val if fee_curr in ['USDT', 'USDC'] else 0.0

                if raw_type in ['buy', 'deposit', 'staking', 'distribution']:
                    add_tx(asset, 'BUY', amt, p_eur, p_usdt, f_eur, f_usdt)
                elif raw_type in ['sell', 'withdrawal']:
                    add_tx(asset, 'SELL', amt, p_eur, p_usdt, f_eur, f_usdt)
        except Exception as e:
            print(f"⚠️ [APP/MAIN] Error reading bitvavo_history: {e}")

        # 2. Parse Cold Wallet On-Chain History
        try:
            cursor.execute("""
                SELECT coin, direction, amount, fee 
                FROM cold_wallet_history 
                ORDER BY timestamp ASC
            """)
            for coin, direction, amount, fee in cursor.fetchall():
                raw_dir = str(direction or '').upper()
                amt = float(amount or 0.0)
                fee_val = float(fee or 0.0)
                
                if raw_dir == 'INBOUND':
                    add_tx(coin, 'BUY', amt, price_eur=0.0, fee_eur=fee_val)
                elif raw_dir == 'OUTBOUND':
                    add_tx(coin, 'SELL', amt, price_eur=0.0, fee_eur=fee_val)
        except Exception as e:
            print(f"⚠️ [APP/MAIN] Error reading cold_wallet_history: {e}")

        # 3. Parse DEGIRO History
        try:
            cursor.execute("""
                SELECT product, isin, aantal, koers, waarde_eur, transactiekosten_eur 
                FROM degiro_history 
                ORDER BY datum ASC, tijd ASC
            """)
            for product, isin, aantal, koers, waarde_eur, txn_fee in cursor.fetchall():
                qty = abs(float(aantal or 0.0))
                unit_price = abs(float(koers or 0.0))
                fee_eur = abs(float(txn_fee or 0.0))
                
                ticker = db_manager.get_cached_ticker(isin) or db_manager.get_cached_ticker(product) or isin or product
                tx_type = 'BUY' if float(aantal or 0.0) > 0 else 'SELL'
                add_tx(ticker, tx_type, qty, unit_price, fee_eur=fee_eur)
        except Exception as e:
            print(f"⚠️ [APP/MAIN] Error reading degiro_history: {e}")

        # 4. Parse Trade Republic History
        try:
            cursor.execute("""
                SELECT symbol, name, type, shares, price, fee 
                FROM trade_republic_history 
                ORDER BY datetime ASC
            """)
            for symbol, name, t_type, shares, price, fee in cursor.fetchall():
                ticker = symbol or db_manager.get_cached_ticker(name) or name
                qty = abs(float(shares or 0.0))
                unit_price = abs(float(price or 0.0))
                fee_eur = abs(float(fee or 0.0))
                
                raw_type = str(t_type or '').lower()
                tx_type = 'SELL' if 'sell' in raw_type or 'verkauf' in raw_type else 'BUY'
                
                add_tx(ticker, tx_type, qty, unit_price, fee_eur=fee_eur)
        except Exception as e:
            print(f"⚠️ [APP/MAIN] Error reading trade_republic_history: {e}")

        conn.close()

        # 5. Execute calculate_cost_basis_summary for each asset
        asset_summaries = {}
        for asset_key, tx_list in asset_tx_map.items():
            asset_summaries[asset_key] = calculate_cost_basis_summary(tx_list)

        return asset_summaries

    except Exception as e:
        print(f"⚠️ [APP/MAIN] Global cost basis processing error: {e}")
        return {}

def resolve_sector(ticker_or_id, sector_map, fallback="Equity"):
    """
    Multi-stage fallback lookup for sector classification:
    1. Direct match on ticker/identifier in sector_map
    2. Cleaned ticker match (stripped of .AS, .DE, exchange suffixes)
    3. Fallback default
    """
    if not ticker_or_id:
        return fallback

    raw_key = str(ticker_or_id).strip().upper()
    if raw_key in sector_map:
        return sector_map[raw_key]

    clean_key = clean_symbol(raw_key)
    if clean_key in sector_map:
        return sector_map[clean_key]

    for k, sec in sector_map.items():
        if k and (k in raw_key or raw_key in k):
            return sec

    return fallback

# --- SIDEBAR: SYNC & ACTIONS ---
st.sidebar.header("⚙️ Data Synchronization")

if st.sidebar.button("🔄 Sync All Ledgers & Prices Now"):
    with st.spinner("Step 1/2: Ingesting transaction history..."):
        try:
            sync_bitvavo()
            st.sidebar.success("Bitvavo synced!")
        except Exception as e:
            st.sidebar.warning(f"Bitvavo sync skipped: {e}")

        try:
            sync_all_wallets()
            st.sidebar.success("Cold wallets synced!")
        except Exception as e:
            st.sidebar.warning(f"Cold wallets skipped: {e}")

        try:
            sync_stocks()
            st.sidebar.success("Stocks synced!")
        except Exception as e:
            st.sidebar.warning(f"Stock sync skipped: {e}")

    with st.spinner("Step 2/2: Backfilling & Caching Historical Prices..."):
        try:
            # 🌟 Integrated master orchestrator call here 🌟
            sync_all_portfolio_prices(
                db_manager=db_manager,
                stock_service=stock_service,
                crypto_service=crypto_service,
                default_start_date="2023-01-01"
            )
            st.sidebar.success("Historical prices fully updated!")
        except Exception as e:
            st.sidebar.error(f"Price sync error: {e}")

# --- LOAD LIVE ASSET BALANCES ---
@st.cache_data(ttl=300)
def load_live_balances():
    sector_map = get_stock_sector_map()
    cost_basis_map = get_asset_cost_bases()

    try:
        bitvavo = BitvavoConnector()
        bv_balances = bitvavo.get_balance() or []
    except Exception as e:
        st.sidebar.warning(f"Bitvavo connector issue: {e}")
        bv_balances = []

    try:
        cold_balances = sync_all_wallets() or {}
    except Exception as e:
        st.sidebar.warning(f"Cold wallets sync issue: {e}")
        cold_balances = {}
        
    try:
        stock_balances = sync_stocks() or {}
    except Exception as e:
        st.sidebar.warning(f"Stock broker connector issue: {e}")
        stock_balances = {}

    holdings_records = []
    live_crypto_val = 0.0
    live_stock_val = 0.0
    total_crypto_cost = 0.0
    total_stock_cost = 0.0

    # 1. Bitvavo Exchange
    if isinstance(bv_balances, list):
        for asset in bv_balances:
            available_qty = float(asset.get('available', 0) or 0)
            staked_qty = float(asset.get('inOrder', 0) or 0)
            total_qty = available_qty + staked_qty
            
            if total_qty > 0.0001: 
                symbol = asset['symbol'].upper()
                if symbol == 'EUR':
                    continue
                price = crypto_service.get_eur_price(symbol)
                eur_val = total_qty * price
                live_crypto_val += eur_val

                summary = cost_basis_map.get(symbol, {})
                avg_buy_price = summary.get('avg_unit_cost_eur', 0.0)
                total_cost = total_qty * avg_buy_price
                total_crypto_cost += total_cost
                pnl_eur = eur_val - total_cost
                pnl_pct = (pnl_eur / total_cost * 100) if total_cost > 0 else 0.0

                holdings_records.append({
                    "Source": "EXCHANGE",
                    "Asset": symbol,
                    "Type": "Crypto",
                    "Sector": "Crypto",
                    "Quantity": total_qty,
                    "Price (EUR)": price,
                    "Avg Buy Price (EUR)": avg_buy_price,
                    "Total Value (EUR)": eur_val,
                    "Profit/Loss (EUR)": pnl_eur,
                    "Profit/Loss (%)": pnl_pct
                })

    # 2. Cold Wallets
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)) and status > 0.0001:
            symbol = coin.upper()
            price = crypto_service.get_eur_price(symbol)
            eur_val = status * price
            live_crypto_val += eur_val

            summary = cost_basis_map.get(symbol, {})
            avg_buy_price = summary.get('avg_unit_cost_eur', 0.0)
            total_cost = status * avg_buy_price
            total_crypto_cost += total_cost
            pnl_eur = eur_val - total_cost
            pnl_pct = (pnl_eur / total_cost * 100) if total_cost > 0 else 0.0

            holdings_records.append({
                "Source": "COLD WALLET",
                "Asset": symbol,
                "Type": "Crypto",
                "Sector": "Crypto",
                "Quantity": status,
                "Price (EUR)": price,
                "Avg Buy Price (EUR)": avg_buy_price,
                "Total Value (EUR)": eur_val,
                "Profit/Loss (EUR)": pnl_eur,
                "Profit/Loss (%)": pnl_pct
            })

    # 3. Stocks & Equities
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ticker, details in stock_balances.items():
        qty = 0.0
        if isinstance(details, dict):
            qty = float(details.get('shares', details.get('quantity', 0)))
        elif isinstance(details, (int, float)):
            qty = float(details)

        if qty > 0.0001:
            ticker_upper = ticker.upper()
            price = 0.0
            try:
                price = stock_service.get_price_on_date(ticker, today_str, preferred_currency="EUR")
            except Exception:
                price = 0.0
                
            eur_val = qty * price
            live_stock_val += eur_val

            sector = resolve_sector(ticker, sector_map, fallback="Equity")
            summary = cost_basis_map.get(ticker_upper, {})
            avg_buy_price = summary.get('avg_unit_cost_eur', 0.0)
            total_cost = qty * avg_buy_price
            total_stock_cost += total_cost
            pnl_eur = eur_val - total_cost
            pnl_pct = (pnl_eur / total_cost * 100) if total_cost > 0 else 0.0

            holdings_records.append({
                "Source": "BROKERAGE",
                "Asset": ticker_upper,
                "Type": "Stock",
                "Sector": sector,
                "Quantity": qty,
                "Price (EUR)": price,
                "Avg Buy Price (EUR)": avg_buy_price,
                "Total Value (EUR)": eur_val,
                "Profit/Loss (EUR)": pnl_eur,
                "Profit/Loss (%)": pnl_pct
            })

    df = pd.DataFrame(holdings_records)
    totals = {
        "crypto_val": live_crypto_val,
        "stock_val": live_stock_val,
        "crypto_cost": total_crypto_cost,
        "stock_cost": total_stock_cost
    }
    return df, totals

with st.spinner("Fetching unified live balance data..."):
    holdings_df, totals = load_live_balances()

crypto_val = totals["crypto_val"]
stock_val = totals["stock_val"]
crypto_cost = totals["crypto_cost"]
stock_cost = totals["stock_cost"]

total_net_worth = crypto_val + stock_val
total_cost = crypto_cost + stock_cost

overall_pnl_pct = ((total_net_worth - total_cost) / total_cost * 100) if total_cost > 0 else 0.0
crypto_pnl_pct = ((crypto_val - crypto_cost) / crypto_cost * 100) if crypto_cost > 0 else 0.0
stock_pnl_pct = ((stock_val - stock_cost) / stock_cost * 100) if stock_cost > 0 else 0.0

# --- TOP KPI METRICS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Net Worth", f"€{total_net_worth:,.2f}", f"{overall_pnl_pct:+.2f}% Profit/Loss")
col2.metric("Crypto Portfolio", f"€{crypto_val:,.2f}", f"{crypto_pnl_pct:+.2f}% Profit/Loss")
col3.metric("Equity Portfolio", f"€{stock_val:,.2f}", f"{stock_pnl_pct:+.2f}% Profit/Loss")
col4.metric("Tracked Assets", f"{len(holdings_df)}")

st.divider()

# --- TOP 8 GROUPING HELPER ---
def get_top_8_df(df_sub):
    if df_sub.empty:
        return df_sub
    
    aggregated = df_sub.groupby("Asset")["Total Value (EUR)"].sum().reset_index()
    aggregated = aggregated.sort_values(by="Total Value (EUR)", ascending=False)
    
    if len(aggregated) <= 8:
        return aggregated
    
    top_7 = aggregated.iloc[:7]
    other_val = aggregated.iloc[7:]["Total Value (EUR)"].sum()
    
    other_row = pd.DataFrame([{"Asset": "Other", "Total Value (EUR)": other_val}])
    return pd.concat([top_7, other_row], ignore_index=True)

# --- TABS NAVIGATION ---
tab_overview, tab_timeline, tab_analyst = st.tabs([
    "📊 Portfolio Holdings", 
    "📈 Historical Timeline", 
    "🤖 Sentinel AI Assistant"
])

with tab_overview:
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.subheader("🪙 Crypto Allocation (Top 8)")
        crypto_df = holdings_df[holdings_df["Type"] == "Crypto"] if not holdings_df.empty else pd.DataFrame()
        crypto_pie_df = get_top_8_df(crypto_df)
        
        if not crypto_pie_df.empty and crypto_pie_df["Total Value (EUR)"].sum() > 0:
            fig_crypto = px.pie(
                crypto_pie_df, 
                names="Asset", 
                values="Total Value (EUR)", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_crypto.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_crypto, width="content")
        else:
            st.info("No Crypto assets to display.")

    with chart_col2:
        st.subheader("📈 Stock & Equity Allocation (Top 8)")
        stock_df = holdings_df[holdings_df["Type"] == "Stock"] if not holdings_df.empty else pd.DataFrame()
        stock_pie_df = get_top_8_df(stock_df)
        
        if not stock_pie_df.empty and stock_pie_df["Total Value (EUR)"].sum() > 0:
            fig_stock = px.pie(
                stock_pie_df, 
                names="Asset", 
                values="Total Value (EUR)", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_stock.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_stock, width="content")
        else:
            st.info("No Stock assets found or pricing unavailable.")

    st.divider()

    st.subheader("📋 Complete Asset Ledgers")
    if not holdings_df.empty:
        display_columns = [
            "Source", "Asset", "Type", "Sector", "Quantity", 
            "Price (EUR)", "Avg Buy Price (EUR)", "Total Value (EUR)", 
            "Profit/Loss (EUR)", "Profit/Loss (%)"
        ]
        st.dataframe(
            holdings_df[display_columns].sort_values(by="Total Value (EUR)", ascending=False).style.format({
                "Quantity": "{:,.4f}",
                "Price (EUR)": "€{:,.4f}",
                "Avg Buy Price (EUR)": "€{:,.4f}",
                "Total Value (EUR)": "€{:,.2f}",
                "Profit/Loss (EUR)": "€{:,.2f}",
                "Profit/Loss (%)": "{:+.2f}%"
            }),
            width='content'
        )

with tab_timeline:
    st.subheader("Portfolio Performance Trajectory")

    col1, col2 = st.columns([3, 1])

    with col1:
        # View selector toggle
        view_option = st.segmented_control(
            "Select Asset Class View",
            options=["ALL", "Crypto", "Stocks"],
            default="ALL",
            key="timeline_asset_view_toggle"
        )

    with col2:
        # Manual cache clear button
        if st.button("🔄 Force Refresh Data"):
            fetch_timeline_data.clear()
            st.rerun()

    # ALWAYS fetch and render (Streamlit will return cached data in <1ms on toggle)
    try:
        timeline_data = fetch_timeline_data(analyzer)

        if timeline_data:
            timeline_df = pd.DataFrame(timeline_data)

            # Determine column mapping based on selected view option
            if view_option == "Crypto":
                val_col = 'crypto_value_eur' if 'crypto_value_eur' in timeline_df.columns else 'total_portfolio_value_eur'
                inv_col = 'crypto_invested_eur' if 'crypto_invested_eur' in timeline_df.columns else 'total_invested_eur'
            elif view_option == "Stocks":
                val_col = 'stocks_value_eur' if 'stocks_value_eur' in timeline_df.columns else 'total_portfolio_value_eur'
                inv_col = 'stocks_invested_eur' if 'stocks_invested_eur' in timeline_df.columns else 'total_invested_eur'
            else:  # "ALL"
                val_col = 'total_portfolio_value_eur'
                inv_col = 'total_invested_eur'

            fig_timeline = go.Figure()

            # Net Worth / Current Value Trace
            fig_timeline.add_trace(go.Scatter(
                x=timeline_df['date'],
                y=timeline_df[val_col],
                mode='lines',
                name=f'{view_option} Value (€)',
                line=dict(color='#00CC96', width=2)
            ))

            # Capital Invested Trace
            fig_timeline.add_trace(go.Scatter(
                x=timeline_df['date'],
                y=timeline_df[inv_col],
                mode='lines',
                name=f'{view_option} Invested (€)',
                line=dict(color='#AB63FA', dash='dash')
            ))

            fig_timeline.update_layout(
                title=f"{view_option} Value vs. Capital Invested",
                xaxis_title="Date",
                yaxis_title="EUR (€)",
                hovermode="x unified"
            )

            st.plotly_chart(fig_timeline, width='content')
        else:
            st.info("No timeline data points were returned.")
    except Exception as e:
        st.error(f"Failed to compile historical timeline: {e}")

with tab_analyst:
    st.subheader("Sentinel Analyst Bot")
    st.caption("Ask questions about your ledger, ROI, tax estimations, or position history.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Ask Sentinel (e.g., 'What is my average buy price on BTC?'):"):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing portfolio context..."):
                try:
                    timeline_data = fetch_timeline_data(analyzer)
                    agent = SentinelAnalyst(historical_data=timeline_data)
                    
                    if hasattr(agent, 'get_response'):
                        response = agent.get_response(user_query)
                    else:
                        response = f"Received prompt: '{user_query}'."
                except Exception as e:
                    response = f"Error processing query: {e}"
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})