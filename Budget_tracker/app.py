import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import calendar

st.set_page_config(
    page_title="Personal Finance Hub",
    page_icon="💳",
    layout="wide"
)

# --- ACCOUNT MAP & CATEGORY RULES ---
ACCOUNTS_MAP = {
    "621816574": "Personal Account",
    "430221096": "Geld Damian",
    "819694312": "House Savings",
    "116343354": "To Be Invested",
    "116343362": "Noodpotje",
    "126766568": "Vakantietjes",
    "126766614": "Direct Sparen",
    "Trade Republic": "Trade Republic Cash"
}

CATEGORIES = [
    "Income & Yield",
    "Housing & Utilities",
    "Telecom & Internet",
    "Insurances & Banking",
    "Fitness & Subscriptions",
    "Groceries",
    "Transport & Fuel",
    "Dining & Snacks",
    "Shopping & Clothing",
    "Leisure & Personal",
    "Internal Savings / Transfer",
    "Brokerage & Stocks",
    "Crypto Investments",
    "Internal Transfer (Excluded)",
    "Portfolio / Trading (Excluded)",
    "Uncategorized"
]

MACRO_MAP = {
    "Income & Yield": "Income",
    "Housing & Utilities": "Bills",
    "Insurances & Banking": "Bills",
    "Telecom & Internet": "Subscriptions",
    "Fitness & Subscriptions": "Subscriptions",
    "Internal Savings / Transfer": "Savings",
    "Brokerage & Stocks": "Savings",
    "Crypto Investments": "Savings",
    "Groceries": "Expenses",
    "Transport & Fuel": "Expenses",
    "Dining & Snacks": "Expenses",
    "Shopping & Clothing": "Expenses",
    "Leisure & Personal": "Expenses",
    "Uncategorized": "Expenses",
    "Internal Transfer (Excluded)": "Excluded",
    "Portfolio / Trading (Excluded)": "Excluded"
}

def categorize_bank_row(description, amount):
    desc = str(description).lower()
    amt = float(amount)
    
    # 1. Housing & Rental Payments
    if "mw s faszbender" in desc or "huishoit" in desc:
        return "Housing & Utilities"

    # 2. Internal Savings, Family Transfers & Tikkies
    SAVINGS_ACCOUNTS = [
        "819694312", "116343354", "116343362", "126766568", 
        "126766614", "nl57trbk", "direct sparen", "noodpotje"
    ]
    
    if any(k in desc for k in SAVINGS_ACCOUNTS):
        return "Internal Savings / Transfer"

    # Personal internal account transfers / Tikkies between payment accounts
    PERSONAL_TRANSFERS = ["621816574", "430221096", "suasso lima prado", "tikkie", "betaalverzoek"]
    if any(k in desc for k in PERSONAL_TRANSFERS):
        return "Internal Transfer (Excluded)"

    # 3a. Crypto Platforms
    if any(k in desc for k in ["bitvavo", "coinbase", "binance", "kraken", "bybit", "crypto.com"]):
        return "Crypto Investments"

    # 3b. Traditional Brokerages & Stocks
    if any(k in desc for k in ["trade republic", "degiro", "semmie", "meesman", "interactive brokers", "etoro"]):
        return "Brokerage & Stocks" if amt < 0 else "Internal Savings / Transfer"
        
    # 4. Insurances, Healthcare, Banking & Taxes
    if any(k in desc for k in [
        "abn amro schade", "basispakket", "verzeker", "ominimo", 
        "belastingdienst", "infomedics", "duo", "int card services", 
        "ics", "aevitae", "cz", "zilveren kruis"
    ]):
        return "Insurances & Banking"

    # 5. Groceries & Supermarkets
    if any(k in desc for k in [
        "jumbo", "lidl", "butlon", "albert heijn", "supermarkt", 
        "dirk", "aldi", "plus ", "intermarche", "k-kauppa"
    ]):
        return "Groceries"
        
    # 6. Transport, Fuel & Parking
    if any(k in desc for k in [
        "benzine", "ns reizigers", "ns groep", "parking", "parkeren", 
        "tango", "shell", "washin7", "essent", "tinq", "tamoil", "esso", "avia"
    ]):
        return "Transport & Fuel"
        
    # 7. Telecom, Hosting & Utilities
    if any(k in desc for k in [
        "simpel", "ziggo", "kpn", "odido", "vodafone", "t-mobile", 
        "domain name", "host"
    ]):
        return "Telecom & Internet"
        
    # 8. Fitness & Subscriptions
    if any(k in desc for k in [
        "basic fit", "basic-fit", "hevy", "gym", "spotify", 
        "netflix", "apple.com", "on that ass"
    ]):
        return "Fitness & Subscriptions"
        
    # 9. Dining, Fast Food & Restaurants
    if any(k in desc for k in [
        "smickel", "zinin ijs", "domino", "mcdonalds", "mcdonald's", "mcd ", 
        "dadawan", "cafe", "restaurant", "bistro", "sushi", "cafetaria", "bedrijfsrest"
    ]):
        return "Dining & Snacks"
        
    # 10. Leisure, Events, Hobbies & Nightlife
    if any(k in desc for k in [
        "soenda", "peakz padel", "padel", "celebratix", "ticketmaster", 
        "ticketingpayments", "festivals", "bloemist", "vieren", "vier hoog", 
        "pairi daiza", "planet awesome", "social deal", "hotel", "horizon",
        "ir.ottenbad", "ottenbad", "drift om te dansen", "drift", "subcultuur"
    ]):
        return "Leisure & Personal"
        
    # 11. Shopping & Retail
    if any(k in desc for k in [
        "intertoys", "zalando", "bol.com", "amazon", "hm.com", 
        "primark", "action", "decathlon"
    ]):
        return "Shopping & Clothing"
        
    # 12. Income & Yield
    if any(k in desc for k in ["lisspanel", "creditrente", "salaris", "dividend"]):
        return "Income & Yield"
    elif amt > 0:
        return "Income & Yield"
        
    return "Uncategorized"

def categorize_tr_row(row):
    cat = str(row['category']).upper()
    tr_type = str(row['type']).upper()
    name = str(row.get('name', '')).lower() if pd.notnull(row.get('name')) else ""
    desc = str(row.get('description', '')).lower() if pd.notnull(row.get('description')) else ""
    text = f"{name} {desc}"
    
    # 1. Non-cash portfolio items
    if cat in ['TRADING', 'CORPORATE_ACTION', 'DELIVERY']:
        return "Portfolio / Trading (Excluded)"
        
    # 2. Yield & Earnings
    if tr_type in ['INTEREST_PAYMENT', 'DIVIDEND', 'BENEFITS_SAVEBACK', 'STOCKPERK']:
        return "Income & Yield"
        
    # 3. Transfers / Cash In-Out
    elif tr_type in ['CUSTOMER_INBOUND', 'CUSTOMER_INPAYMENT', 'TRANSFER_INSTANT_INBOUND', 'VIBAN_TRANSFER_INBOUND', 'CUSTOMER_OUTBOUND_REQUEST', 'TRANSFER_INSTANT_OUTBOUND']:
        return "Internal Savings / Transfer"
        
    # 4. Card Transactions
    elif tr_type in ['CARD_TRANSACTION', 'CARD_TRANSACTION_INTERNATIONAL']:
        if any(term in text for term in ["hotel", "ticketmaster", "social deal", "de bootjes", "porto alta", "pittoresk"]):
            return "Leisure & Personal"
        elif any(term in text for term in ["tinq", "esso", "tango", "shell"]):
            return "Transport & Fuel"
        elif any(term in text for term in ["i love sushi", "cafe", "restaurant"]):
            return "Dining & Snacks"
        elif any(term in text for term in ["intertoys", "apple store", "bijou brigitte", "hansanders"]):
            return "Shopping & Clothing"
        elif any(term in text for term in ["jumbo", "lidl", "albert heijn", "supermarkt"]):
            return "Groceries"
        else:
            return "Leisure & Personal"
            
    return "Uncategorized"

# --- APP TITLE ---
st.title("💳 Personal Finance & Zero-Based Budgeting Hub")

# --- SIDEBAR: MULTI-FILE UPLOADER ---
st.sidebar.header("1. Data Ingestion")

uploaded_bank_files = st.sidebar.file_uploader("Upload Bank Files (.xls / .xlsx)", type=["xls", "xlsx"], accept_multiple_files=True)
uploaded_tr_files = st.sidebar.file_uploader("Upload Trade Republic Files (.csv)", type=["csv"], accept_multiple_files=True)

all_records = []

# Process Bank Files
if uploaded_bank_files:
    for b_file in uploaded_bank_files:
        try:
            df_b = pd.read_excel(b_file)
            for _, row in df_b.iterrows():
                dt = pd.to_datetime(str(row['transactiondate']), format='%Y%m%d', errors='coerce')
                amt = float(row['amount'])
                desc = str(row['description'])
                cat = categorize_bank_row(desc, amt)
                
                raw_account = str(row.get('accountNumber', ''))
                account_label = ACCOUNTS_MAP.get(raw_account, raw_account if raw_account else "Bank Account")
                
                all_records.append({
                    "Date": dt,
                    "Source": "Bank",
                    "Account": account_label,
                    "RawAccount": raw_account,
                    "StartSaldo": float(row.get('startsaldo', 0.0)),
                    "EndSaldo": float(row.get('endsaldo', 0.0)),
                    "Amount": amt,
                    "Category": cat,
                    "MacroCategory": MACRO_MAP.get(cat, "Expenses"),
                    "Description": desc
                })
        except Exception as e:
            st.sidebar.error(f"Error reading bank file {b_file.name}: {e}")

# Process Trade Republic Files
if uploaded_tr_files:
    for tr_file in uploaded_tr_files:
        try:
            df_tr = pd.read_csv(tr_file)
            for _, row in df_tr.iterrows():
                dt = pd.to_datetime(row['datetime'], errors='coerce').tz_localize(None)
                amt = float(row['amount']) if pd.notnull(row['amount']) else 0.0
                desc = str(row['description']) if pd.notnull(row['description']) else str(row['type'])
                cat = categorize_tr_row(row)
                
                all_records.append({
                    "Date": dt,
                    "Source": "Trade Republic",
                    "Account": ACCOUNTS_MAP.get("Trade Republic", "Trade Republic Cash"),
                    "RawAccount": "Trade Republic",
                    "StartSaldo": None,
                    "EndSaldo": None,
                    "Amount": amt,
                    "Category": cat,
                    "MacroCategory": MACRO_MAP.get(cat, "Expenses"),
                    "Description": desc
                })
        except Exception as e:
            st.sidebar.error(f"Error reading TR file {tr_file.name}: {e}")

df_transactions = pd.DataFrame(all_records)

if not df_transactions.empty:
    df_transactions['Year'] = df_transactions['Date'].dt.year
    df_transactions['Month_Name'] = df_transactions['Date'].dt.strftime('%b')
    df_transactions['Month_Num'] = df_transactions['Date'].dt.month
    df_transactions.sort_values(by="Date", ascending=True, inplace=True)

# --- TAB NAVIGATION ---
tab_upload, tab_tx, tab_accounts, tab_budget, tab_analytics, tab_monthly = st.tabs([
    "📥 Ingestion Hub", 
    "📝 Transactions", 
    "🏦 Accounts & Savings", 
    "⚖️ Zero-Based Planner", 
    "📊 Dashboard",
    "📅 Monthly Overview"
])

# TAB 1: INGESTION HUB
with tab_upload:
    st.subheader("Data Processing Overview")
    col1, col2, col3 = st.columns(3)
    bank_count = len([r for r in all_records if r['Source'] == 'Bank'])
    tr_count = len([r for r in all_records if r['Source'] == 'Trade Republic'])
    col1.metric("Bank Transactions Ingested", bank_count)
    col2.metric("Trade Republic Records Ingested", tr_count)
    col3.metric("Total Consolidated Records", len(all_records))

# TAB 2: TRANSACTIONS TABLE
with tab_tx:
    st.subheader("Transaction Manager")
    if not df_transactions.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sources = st.multiselect("Filter by Source", options=["Bank", "Trade Republic"], default=["Bank", "Trade Republic"])
        with col_f2:
            cats = st.multiselect("Filter by Category", options=CATEGORIES, default=[])
        
        filtered_df = df_transactions.copy()
        if sources:
            filtered_df = filtered_df[filtered_df['Source'].isin(sources)]
        if cats:
            filtered_df = filtered_df[filtered_df['Category'].isin(cats)]
            
        st.data_editor(
            filtered_df[['Date', 'Source', 'Account', 'Amount', 'Category', 'Description']],
            column_config={
                "Category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, required=True),
                "Amount": st.column_config.NumberColumn("Amount (€)", format="€ %.2f"),
                "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")
            },
            use_container_width=True,
            num_rows="dynamic"
        )
    else:
        st.info("Upload statement files in the sidebar to view transactions.")

# TAB 3: ACCOUNTS & BALANCES
with tab_accounts:
    st.subheader("Account Balances & Funding Overview")
    if not df_transactions.empty and 'Year' in df_transactions.columns:
        available_years = sorted(df_transactions['Year'].dropna().astype(int).unique().tolist())
        selected_year = st.selectbox("Select Reporting Year", options=available_years, index=len(available_years)-1, key="acc_year")
        
        balance_summary = []
        for acc_num, acc_name in ACCOUNTS_MAP.items():
            if acc_num == "Trade Republic":
                tr_cash_df = df_transactions[
                    (df_transactions['RawAccount'] == "Trade Republic") & 
                    (df_transactions['Category'] != 'Portfolio / Trading (Excluded)')
                ].sort_values(by="Date")
                
                if not tr_cash_df.empty:
                    tr_cash_df['cum_amount'] = tr_cash_df['Amount'].cumsum()
                    before_y = tr_cash_df[tr_cash_df['Date'] < pd.Timestamp(f"{selected_year}-01-01")]
                    start_bal = before_y.iloc[-1]['cum_amount'] if not before_y.empty else 0.0
                    
                    df_y = tr_cash_df[tr_cash_df['Year'] == selected_year]
                    if not df_y.empty:
                        latest_bal = df_y.iloc[-1]['cum_amount']
                        latest_date = df_y.iloc[-1]['Date'].strftime('%Y-%m-%d')
                    else:
                        latest_bal = start_bal
                        latest_date = "N/A"
                    net_change = latest_bal - start_bal
                else:
                    start_bal, latest_bal, net_change, latest_date = 0.0, 0.0, 0.0, "N/A"
            else:
                acc_txs = df_transactions[(df_transactions['RawAccount'] == acc_num) & (df_transactions['Year'] == selected_year)].sort_values(by="Date")
                if not acc_txs.empty:
                    start_bal = acc_txs.iloc[0]['StartSaldo']
                    latest_bal = acc_txs.iloc[-1]['EndSaldo']
                    net_change = latest_bal - start_bal
                    latest_date = acc_txs.iloc[-1]['Date'].strftime('%Y-%m-%d')
                else:
                    start_bal, latest_bal, net_change, latest_date = 0.0, 0.0, 0.0, "N/A"
                
            balance_summary.append({
                "Account Number": acc_num,
                "Account Name": acc_name,
                "Start Balance": f"€ {start_bal:,.2f}",
                "Latest Balance": f"€ {latest_bal:,.2f}",
                "Net Growth": f"€ {net_change:,.2f}",
                "Latest Balance Date": latest_date
            })
            
        st.table(pd.DataFrame(balance_summary))
    else:
        st.info("Upload statements to calculate account funding and balances.")

# TAB 4: ZERO-BASED BUDGET PLANNER
with tab_budget:
    st.subheader("Zero-Based Monthly Planner")
    if not df_transactions.empty:
        cash_txs = df_transactions[~df_transactions['Category'].isin(['Portfolio / Trading (Excluded)', 'Internal Transfer (Excluded)'])]
        
        total_income = cash_txs[cash_txs['Amount'] > 0]['Amount'].sum()
        total_transfers = abs(cash_txs[cash_txs['Category'] == 'Internal Savings / Transfer']['Amount'].sum())
        total_expenses = abs(cash_txs[(cash_txs['Amount'] < 0) & (cash_txs['Category'] != 'Internal Savings / Transfer')]['Amount'].sum())
        
        leftover = total_income - total_expenses - total_transfers
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Inflow", f"€{total_income:,.2f}")
        m2.metric("Living Expenses", f"€{total_expenses:,.2f}")
        m3.metric("Savings / Transfers Out", f"€{total_transfers:,.2f}")
        m4.metric("Unassigned Cash", f"€{leftover:,.2f}", delta="Zero-Based Target: €0.00")
        
        pct_used = min(1.0, max(0.0, (total_expenses + total_transfers) / total_income)) if total_income > 0 else 0.0
        st.progress(pct_used)
    else:
        st.info("Upload statement files to view zero-based metric calculations.")

# TAB 5: DASHBOARD
with tab_analytics:
    st.subheader("Analytics & Financial Overview")
    if not df_transactions.empty:
        available_years = sorted(df_transactions['Year'].dropna().astype(int).unique().tolist())
        selected_dash_year = st.selectbox("Select Year", options=available_years, index=len(available_years)-1, key="dash_year")
        
        df_year = df_transactions[df_transactions['Year'] == selected_dash_year].copy()
        
        spend_df = df_year[
            (df_year['Amount'] < 0) & 
            (~df_year['Category'].isin(['Internal Savings / Transfer', 'Internal Transfer (Excluded)', 'Portfolio / Trading (Excluded)']))
        ].copy()
        spend_df['Expense_Amount'] = spend_df['Amount'].abs()
        
        if not spend_df.empty:
            dash_col1, dash_col2 = st.columns(2)
            
            # --- MACRO CATEGORY OVERVIEW ---
            with dash_col1:
                st.markdown("### **SPENDING OVERVIEW**")
                macro_dash = spend_df.groupby('MacroCategory')['Expense_Amount'].sum().reset_index()
                fig_dash_macro = px.pie(
                    macro_dash,
                    values='Expense_Amount',
                    names='MacroCategory',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_dash_macro.update_traces(
                    textposition='outside', 
                    textinfo='label+percent'
                )
                fig_dash_macro.update_layout(
                    margin=dict(t=80, b=80, l=120, r=120), 
                    showlegend=False
                )
                st.plotly_chart(fig_dash_macro, use_container_width=True)

            # --- GRANULAR SUB-CATEGORY SPENDING ---
            with dash_col2:
                st.markdown("### **WHERE DOES MY MONEY GO?**")
                breakdown_df = spend_df.groupby('Category')['Expense_Amount'].sum().reset_index()
                fig_dash_sub = px.pie(
                    breakdown_df, 
                    values='Expense_Amount', 
                    names='Category', 
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_dash_sub.update_traces(
                    textposition='outside', 
                    textinfo='label+percent'
                )
                fig_dash_sub.update_layout(
                    margin=dict(t=80, b=80, l=120, r=120), 
                    showlegend=False
                )
                st.plotly_chart(fig_dash_sub, use_container_width=True)
                
            # --- DASHBOARD BREAKDOWN TABLE ---
            st.markdown("#### **WHERE DOES MY MONEY GO ? (SUMMARY TABLE)**")
            dash_tbl = breakdown_df.copy()
            total_dash_spend = dash_tbl['Expense_Amount'].sum()
            dash_tbl['PERC.'] = (dash_tbl['Expense_Amount'] / total_dash_spend * 100).round(1).astype(str) + "%"
            dash_tbl = dash_tbl.sort_values(by='Expense_Amount', ascending=False)
            dash_tbl.columns = ['SUB-CATEGORY', 'REAL', 'PERC.']
            dash_tbl['REAL'] = dash_tbl['REAL'].apply(lambda x: f"€ {x:,.2f}")
            st.dataframe(dash_tbl, hide_index=True, use_container_width=True)
            
        else:
            st.info("No spending transactions found for the selected year.")
            
        st.divider()
        
        st.markdown("### **ANNUAL INCOME vs EXPENSES**")
        months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        monthly_inc = df_year[
            (df_year['Amount'] > 0) & 
            (~df_year['Category'].isin(['Portfolio / Trading (Excluded)', 'Internal Transfer (Excluded)']))
        ].groupby('Month_Name')['Amount'].sum()
        
        monthly_exp = spend_df.groupby('Month_Name')['Expense_Amount'].sum()
        monthly_df = pd.DataFrame({'Inflows / Income': monthly_inc, 'Expenses': monthly_exp}).reindex(months_order).fillna(0)
        
        fig_inc_exp = go.Figure()
        fig_inc_exp.add_trace(go.Bar(
            x=monthly_df.index,
            y=monthly_df['Expenses'],
            name='TOTAL EXPENSES',
            marker_color='#F7C59F'
        ))
        fig_inc_exp.add_trace(go.Scatter(
            x=monthly_df.index,
            y=monthly_df['Inflows / Income'],
            name='TOTAL INFLOWS',
            mode='lines',
            fill='tozeroy',
            fillcolor='rgba(168, 218, 220, 0.3)',
            line=dict(color='#2A9D8F', shape='spline', width=3)
        ))
        fig_inc_exp.update_layout(
            xaxis_title="Month",
            yaxis_title="Amount (€)",
            barmode='group',
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_inc_exp, use_container_width=True)
        
        st.divider()
        
        st.markdown("### **INVESTMENTS & SAVINGS TRACKER**")
        col_inv, col_sav = st.columns(2)
        inv_df = df_year[df_year['Category'].isin(['Brokerage & Stocks', 'Crypto Investments'])].copy()
        inv_df['Amount'] = inv_df['Amount'].abs()
        
        with col_inv:
            st.markdown("**Monthly Investments**")
            if not inv_df.empty:
                monthly_inv = inv_df.groupby(['Month_Name', 'Category'])['Amount'].sum().reset_index()
                fig_inv = px.bar(
                    monthly_inv, 
                    x='Month_Name', 
                    y='Amount', 
                    color='Category',
                    category_orders={"Month_Name": months_order},
                    color_discrete_map={'Brokerage & Stocks': '#2A9D8F', 'Crypto Investments': '#F4A261'},
                    labels={'Amount': 'Amount (€)', 'Month_Name': 'Month'}
                )
                fig_inv.update_layout(template='plotly_white')
                st.plotly_chart(fig_inv, use_container_width=True)
            else:
                st.info("No investment records found for this year.")
                
        sav_df = df_year[(df_year['Category'] == 'Internal Savings / Transfer') & (df_year['Amount'] < 0)].copy()
        sav_df['Amount'] = sav_df['Amount'].abs()
        
        with col_sav:
            st.markdown("**Monthly Savings Outflows**")
            if not sav_df.empty:
                monthly_sav = sav_df.groupby('Month_Name')['Amount'].sum().reindex(months_order).fillna(0).reset_index()
                fig_sav = px.bar(
                    monthly_sav, 
                    x='Month_Name', 
                    y='Amount',
                    category_orders={"Month_Name": months_order},
                    color_discrete_sequence=['#4EA8DE'],
                    labels={'Amount': 'Amount (€)', 'Month_Name': 'Month'}
                )
                fig_sav.update_layout(template='plotly_white')
                st.plotly_chart(fig_sav, use_container_width=True)
            else:
                st.info("No savings/transfer records found for this year.")

    else:
        st.info("No transaction data loaded for dashboard visual display.")

# TAB 6: MONTHLY OVERVIEW
with tab_monthly:
    st.subheader("Monthly Granular Overview")
    if not df_transactions.empty:
        col_m1, col_m2 = st.columns(2)
        available_years = sorted(df_transactions['Year'].dropna().astype(int).unique().tolist())
        
        with col_m1:
            sel_m_year = st.selectbox("Select Year", options=available_years, index=len(available_years)-1, key="m_year")
        with col_m2:
            month_list = [calendar.month_name[i] for i in range(1, 13)]
            sel_m_month_str = st.selectbox("Select Month", options=month_list, index=0, key="m_month")
            sel_m_month = month_list.index(sel_m_month_str) + 1

        df_m = df_transactions[
            (df_transactions['Year'] == sel_m_year) & 
            (df_transactions['Month_Num'] == sel_m_month) &
            (~df_transactions['Category'].isin(['Portfolio / Trading (Excluded)', 'Internal Transfer (Excluded)']))
        ].copy()

        m_income = df_m[df_m['Amount'] > 0]['Amount'].sum()
        m_expenses = abs(df_m[df_m['Amount'] < 0]['Amount'].sum())

        kpi1, kpi2 = st.columns(2)
        kpi1.metric("Total Inflow (Income & Transfers In)", f"€ {m_income:,.2f}")
        kpi2.metric("Total Outflow (Expenses & Transfers Out)", f"€ {m_expenses:,.2f}")

        st.divider()

        # --- FIGURE 1: BALANCE OVERVIEW ---
        st.markdown("### **BALANCE OVERVIEW**")
        num_days = calendar.monthrange(sel_m_year, sel_m_month)[1]
        all_days = pd.date_range(start=f"{sel_m_year}-{sel_m_month:02d}-01", periods=num_days, freq='D')
        
        daily_df = pd.DataFrame({'Date': all_days})
        
        if not df_m.empty:
            df_m_daily = df_m.groupby(df_m['Date'].dt.date).agg(
                Income=('Amount', lambda x: x[x > 0].sum()),
                Total_Exp=('Amount', lambda x: abs(x[x < 0].sum())),
                Net=('Amount', 'sum')
            ).reset_index()
            df_m_daily['Date'] = pd.to_datetime(df_m_daily['Date'])
            daily_df = pd.merge(daily_df, df_m_daily, on='Date', how='left').fillna(0)
        else:
            daily_df['Income'] = 0.0
            daily_df['Total_Exp'] = 0.0
            daily_df['Net'] = 0.0

        daily_df['Balance'] = daily_df['Net'].cumsum()
        daily_df['Date_Str'] = daily_df['Date'].dt.strftime('%-d-%b')

        fig_bal = go.Figure()
        fig_bal.add_trace(go.Scatter(
            x=daily_df['Date_Str'],
            y=daily_df['Balance'],
            mode='lines',
            fill='tozeroy',
            fillcolor='rgba(224, 242, 254, 0.5)',
            line=dict(color='#38BDF8', width=2),
            name="Balance"
        ))
        fig_bal.update_layout(
            template='plotly_white',
            margin=dict(t=20, b=20, l=20, r=20),
            yaxis_title="Balance (€)",
            xaxis_title="Date"
        )
        st.plotly_chart(fig_bal, use_container_width=True)

        st.divider()

        # --- FIGURE 2: SPENDING OVERVIEW (MACRO CATEGORIES) ---
        st.markdown("### **SPENDING OVERVIEW**")
        m_outflows = df_m[df_m['Amount'] < 0].copy()
        m_outflows['Abs_Amount'] = m_outflows['Amount'].abs()

        if not m_outflows.empty:
            macro_summary = m_outflows.groupby('MacroCategory')['Abs_Amount'].sum().reset_index()
            fig_macro = px.pie(
                macro_summary,
                values='Abs_Amount',
                names='MacroCategory',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_macro.update_traces(
                textposition='outside', 
                textinfo='label+percent'
            )
            fig_macro.update_layout(
                showlegend=False, 
                margin=dict(t=80, b=80, l=120, r=120)
            )
            st.plotly_chart(fig_macro, use_container_width=True)
        else:
            st.info("No outflows recorded for this month.")

        st.divider()

        # --- FIGURE 3: WHERE DOES MY MONEY GO? & WHEN DO I SPEND / RECEIVE MY MONEY? ---
        col_fig3_left, col_fig3_right = st.columns(2)

        with col_fig3_left:
            st.markdown("### **WHERE DOES MY MONEY GO?**")
            if not m_outflows.empty:
                cat_summary = m_outflows.groupby('Category')['Abs_Amount'].sum().reset_index()
                fig_subcat = px.pie(
                    cat_summary,
                    values='Abs_Amount',
                    names='Category',
                    hole=0.5,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_subcat.update_traces(
                    textposition='outside', 
                    textinfo='label+percent'
                )
                fig_subcat.update_layout(
                    showlegend=False, 
                    margin=dict(t=80, b=80, l=120, r=120)
                )
                st.plotly_chart(fig_subcat, use_container_width=True)
            else:
                st.info("No outflow data for sub-category distribution.")

        with col_fig3_right:
            st.markdown("### **WHEN DO I SPEND / RECEIVE MY MONEY?**")
            
            # Subplot with secondary y-axis restored
            fig_when = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Spent Bars (Left Axis)
            fig_when.add_trace(
                go.Bar(
                    x=daily_df['Date_Str'],
                    y=daily_df['Total_Exp'],
                    name='Spent (Outflows)',
                    marker_color='#F7C59F',
                    marker_line_color='#E76F51',
                    marker_line_width=1
                ),
                secondary_y=False
            )
            
            # Received Bars (Right Axis)
            fig_when.add_trace(
                go.Bar(
                    x=daily_df['Date_Str'],
                    y=daily_df['Income'],
                    name='Received (Inflows)',
                    marker_color='#2A9D8F',
                    marker_line_color='#264653',
                    marker_line_width=1
                ),
                secondary_y=True
            )

            max_exp = max(daily_df['Total_Exp'].max(), 100)
            max_inc = max(daily_df['Income'].max(), 100)

            fig_when.update_layout(
                template='plotly_white',
                barmode='group',
                bargap=0.15,
                bargroupgap=0.05,
                margin=dict(t=40, b=20, l=20, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            fig_when.update_xaxes(title_text="Date")
            
            fig_when.update_yaxes(
                title_text="Expenses (€)", 
                secondary_y=False, 
                range=[0, max_exp * 1.1],
                nticks=6,
                showgrid=True
            )
            fig_when.update_yaxes(
                title_text="Inflows (€)", 
                secondary_y=True, 
                range=[0, max_inc * 1.1],
                nticks=6,
                showgrid=False
            )

            st.plotly_chart(fig_when, use_container_width=True)

        st.divider()

        # --- FIGURE 4: ACCOMPANIED TABLES ---
        col_tbl_left, col_tbl_right = st.columns(2)

        with col_tbl_left:
            st.markdown("#### **WHERE DOES MY MONEY GO ?**")
            if not m_outflows.empty:
                subcat_tbl = m_outflows.groupby('Category')['Abs_Amount'].sum().reset_index()
                tot_outflow = subcat_tbl['Abs_Amount'].sum()
                subcat_tbl['PERC.'] = (subcat_tbl['Abs_Amount'] / tot_outflow * 100).round(1).astype(str) + "%"
                subcat_tbl = subcat_tbl.sort_values(by='Abs_Amount', ascending=False)
                subcat_tbl.columns = ['SUB-CATEGORY', 'REAL', 'PERC.']
                subcat_tbl['REAL'] = subcat_tbl['REAL'].apply(lambda x: f"€ {x:,.2f}")
                st.dataframe(subcat_tbl, hide_index=True, use_container_width=True)
            else:
                st.info("No spending records.")

        with col_tbl_right:
            st.markdown("#### **WHEN DO I SPEND / RECEIVE MY MONEY ?**")
            tbl_when = daily_df[['Date_Str', 'Income', 'Total_Exp', 'Balance']].copy()
            tbl_when.columns = ['DATE', 'INFLOW', 'TOTAL EXP.', 'BALANCE']
            tbl_when['INFLOW'] = tbl_when['INFLOW'].apply(lambda x: f"€ {x:,.2f}")
            tbl_when['TOTAL EXP.'] = tbl_when['TOTAL EXP.'].apply(lambda x: f"€ {x:,.2f}")
            tbl_when['BALANCE'] = tbl_when['BALANCE'].apply(lambda x: f"€ {x:,.2f}")
            st.dataframe(tbl_when, hide_index=True, use_container_width=True, height=400)

        st.divider()

        # --- FIGURE 5: FILTERED TRANSACTIONS ---
        st.markdown("### **FILTERED TRANSACTIONS**")
        
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            m_cats = st.multiselect("Filter by Sub-Category", options=CATEGORIES, default=[], key="m_subcat_filter")
        with f_col2:
            m_macro = st.multiselect("Filter by Category Bucket", options=["Expenses", "Savings", "Bills", "Subscriptions", "Income"], default=[], key="m_macro_filter")

        tx_m_filtered = df_m.copy()
        if m_cats:
            tx_m_filtered = tx_m_filtered[tx_m_filtered['Category'].isin(m_cats)]
        if m_macro:
            tx_m_filtered = tx_m_filtered[tx_m_filtered['MacroCategory'].isin(m_macro)]

        tot_filtered_amt = abs(tx_m_filtered['Amount'].sum())
        st.metric("Filtered Total Amount", f"€ {tot_filtered_amt:,.2f}")

        display_tx = tx_m_filtered[['Date', 'Amount', 'Category', 'MacroCategory', 'Account', 'Description']].copy()
        display_tx.columns = ['DATE', 'AMOUNT', 'SUB-CATEGORY', 'CATEGORY', 'ACCOUNT PROVENANCE', 'DESCRIPTION']

        st.dataframe(
            display_tx,
            column_config={
                "AMOUNT": st.column_config.NumberColumn("AMOUNT", format="€ %.2f"),
                "DATE": st.column_config.DateColumn("DATE", format="YYYY-MM-DD")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Upload statement files to view the monthly detailed overview.")