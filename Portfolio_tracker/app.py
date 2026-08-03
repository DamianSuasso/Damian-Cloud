import sys
import os
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
from Portfolio_tracker.utils.crypto_price_service import Crypto_PriceService
from Portfolio_tracker.utils.stock_price_service import StockPriceService
from Portfolio_tracker.utils.analyzer import PortfolioAnalyzer
from Portfolio_tracker.agents.analyst import SentinelAnalyst

from Portfolio_tracker.sync_crypto import sync_bitvavo
from Portfolio_tracker.sync_cold_wallets import sync_all_wallets
from Portfolio_tracker.sync_stocks import sync_stocks

st.set_page_config(page_title="Sentinel Portfolio Console", layout="wide", page_icon="🛡️")

# Custom CSS to keep metric card fonts clean and readable
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ Sentinel Portfolio Console")
st.caption("Live Unified Dashboard: Crypto, Equities & Cold Storage")

# --- SIDEBAR: SYNC & ACTIONS ---
st.sidebar.header("⚙️ Data Synchronization")

if st.sidebar.button("🔄 Sync All Ledgers Now"):
    with st.spinner("Syncing Bitvavo, Cold Wallets, and Equities..."):
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

# --- CACHED HEAVY LOADERS ---
@st.cache_resource
def get_price_engines():
    price_engine = Crypto_PriceService()
    stock_price_engine = StockPriceService()
    return price_engine, stock_price_engine

price_engine, stock_price_engine = get_price_engines()

# Instantiate fresh analyzer instance to avoid cross-thread SQLite sharing errors
analyzer = PortfolioAnalyzer()

# --- LOAD LIVE ASSET BALANCES ---
@st.cache_data(ttl=300)
def load_live_balances():
    try:
        bitvavo = BitvavoConnector()
        bv_balances = bitvavo.get_balance() or []
    except Exception as e:
        st.sidebar.warning(f"Bitvavo connector issue: {e}")
        bv_balances = []

    try:
        cold_balances = sync_all_wallets() or {}
    except Exception:
        cold_balances = {}
        
    try:
        stock_balances = sync_stocks() or {}
    except Exception:
        stock_balances = {}

    holdings_records = []
    live_crypto_val = 0.0
    live_stock_val = 0.0

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
                price = price_engine.get_eur_price(symbol)
                eur_val = total_qty * price
                live_crypto_val += eur_val
                holdings_records.append({
                    "Source": "EXCHANGE",
                    "Asset": symbol,
                    "Type": "Crypto",
                    "Quantity": total_qty,
                    "Price (EUR)": price,
                    "Total Value (EUR)": eur_val
                })

    # 2. Cold Wallets
    for coin, status in cold_balances.items():
        if isinstance(status, (int, float)) and status > 0.0001:
            price = price_engine.get_eur_price(coin)
            eur_val = status * price
            live_crypto_val += eur_val
            holdings_records.append({
                "Source": "COLD WALLET",
                "Asset": coin,
                "Type": "Crypto",
                "Quantity": status,
                "Price (EUR)": price,
                "Total Value (EUR)": eur_val
            })

    # 3. Stocks & Equities
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ticker, details in stock_balances.items():
        qty = 0.0
        # Check dictionary format vs direct number format
        if isinstance(details, dict):
            qty = float(details.get('shares', details.get('quantity', 0)))
        elif isinstance(details, (int, float)):
            qty = float(details)

        if qty > 0.0001:
            price = 0.0
            try:
                price = stock_price_engine.get_price_on_date(ticker, today_str, preferred_currency="EUR")
            except Exception:
                price = 0.0
                
            eur_val = qty * price
            live_stock_val += eur_val
            holdings_records.append({
                "Source": "BROKERAGE",
                "Asset": ticker,
                "Type": "Stock",
                "Quantity": qty,
                "Price (EUR)": price,
                "Total Value (EUR)": eur_val
            })

    df = pd.DataFrame(holdings_records)
    return df, live_crypto_val, live_stock_val

with st.spinner("Fetching unified live balance data..."):
    holdings_df, crypto_val, stock_val = load_live_balances()

total_net_worth = crypto_val + stock_val

# --- TOP KPI METRICS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Net Worth", f"€{total_net_worth:,.2f}")
col2.metric("Crypto Allocation", f"€{crypto_val:,.2f}", f"{(crypto_val/total_net_worth*100 if total_net_worth else 0):.1f}%")
col3.metric("Equity Allocation", f"€{stock_val:,.2f}", f"{(stock_val/total_net_worth*100 if total_net_worth else 0):.1f}%")
col4.metric("Tracked Assets", f"{len(holdings_df)}")

st.divider()

# --- TOP 8 GROUPING HELPER ---
def get_top_8_df(df_sub):
    """Groups top 7 assets and aggregates the remainder under 'Other'."""
    if df_sub.empty:
        return df_sub
    
    # Aggregate total values by Asset (handles multiple entries across sources)
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
    # 1. Dual Pie Charts Row (Top 8 entries max per chart)
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
            st.plotly_chart(fig_crypto, use_container_width=True)
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
            st.plotly_chart(fig_stock, use_container_width=True)
        else:
            st.info("No Stock assets found or pricing unavailable.")

    st.divider()

    # 2. Detailed Unified Table (Unfiltered listing of all holdings)
    st.subheader("📋 Complete Asset Ledgers")
    if not holdings_df.empty:
        st.dataframe(
            holdings_df.sort_values(by="Total Value (EUR)", ascending=False).style.format({
                "Quantity": "{:,.4f}",
                "Price (EUR)": "€{:,.4f}",
                "Total Value (EUR)": "€{:,.2f}"
            }),
            use_container_width=True
        )

with tab_timeline:
    st.subheader("Portfolio Performance Trajectory")
    
    if st.button("Load/Refresh Timeline Graph"):
        with st.spinner("Compiling historical timeline data..."):
            try:
                analyzer.warm_up_price_cache(start_year=2023)
                timeline_data = analyzer.get_portfolio_historical_timeline()
                
                if timeline_data:
                    timeline_df = pd.DataFrame(timeline_data)
                    
                    fig_timeline = go.Figure()
                    fig_timeline.add_trace(go.Scatter(
                        x=timeline_df['date'], 
                        y=timeline_df['total_portfolio_value_eur'],
                        mode='lines',
                        name='Net Worth (€)',
                        line=dict(color='#00CC96', width=2)
                    ))
                    fig_timeline.add_trace(go.Scatter(
                        x=timeline_df['date'], 
                        y=timeline_df['total_invested_eur'],
                        mode='lines',
                        name='Total Invested (€)',
                        line=dict(color='#AB63FA', dash='dash')
                    ))
                    fig_timeline.update_layout(
                        title="Net Worth vs. Capital Invested",
                        xaxis_title="Date",
                        yaxis_title="EUR (€)",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_timeline, use_container_width=True)
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
                    timeline_data = analyzer.get_portfolio_historical_timeline()
                    agent = SentinelAnalyst(historical_data=timeline_data)
                    
                    if hasattr(agent, 'get_response'):
                        response = agent.get_response(user_query)
                    else:
                        response = f"Received prompt: '{user_query}'."
                except Exception as e:
                    response = f"Error processing query: {e}"
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})