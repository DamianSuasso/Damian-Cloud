import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
    "Portfolio / Trading (Excluded)",
    "Uncategorized"
]

def categorize_bank_row(description, amount):
    desc = str(description).lower()
    amt = float(amount)
    
    # 1. Housing & Rental Payments
    if "mw s faszbender" in desc or "huishoit" in desc:
        return "Housing & Utilities"

    # 2. Internal Savings, Family Transfers & Tikkies
    ACCOUNTS_AND_NAMES = [
        "621816574", "430221096", "819694312", "116343354", 
        "116343362", "126766568", "126766614", "suasso lima prado", 
        "tikkie", "betaalverzoek"
    ]
    if any(k in desc for k in ACCOUNTS_AND_NAMES):
        return "Internal Savings / Transfer"

    # 3a. Crypto Platforms
    if any(k in desc for k in ["bitvavo", "coinbase", "binance", "kraken", "bybit", "crypto.com"]):
        return "Crypto Investments"

    # 3b. Traditional Brokerages & Stocks
    if any(k in desc for k in ["trade republic", "degiro", "semmie", "meesman", "interactive brokers", "etoro"]):
        return "Brokerage & Stocks"
        
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
    
    # 1. Non-cash portfolio items (Trading, Corporate Actions, Deliveries)
    if cat in ['TRADING', 'CORPORATE_ACTION', 'DELIVERY']:
        return "Portfolio / Trading (Excluded)"
        
    # 2. Yield & Earnings
    if tr_type in ['INTEREST_PAYMENT', 'DIVIDEND', 'BENEFITS_SAVEBACK', 'STOCKPERK']:
        return "Income & Yield"
        
    # 3. Transfers / Cash In-Out
    elif tr_type in ['CUSTOMER_INBOUND', 'CUSTOMER_INPAYMENT', 'TRANSFER_INSTANT_INBOUND', 'VIBAN_TRANSFER_INBOUND', 'CUSTOMER_OUTBOUND_REQUEST', 'TRANSFER_INSTANT_OUTBOUND']:
        if any(term in text for term in ["suasso", "sent from", "to be invested", "loan savings", "n26", "citideff"]):
            return "Internal Savings / Transfer"
        return "Income & Yield"
        
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
                all_records.append({
                    "Date": dt,
                    "Source": "Bank",
                    "Account": str(row.get('accountNumber', 'Bank Account')),
                    "StartSaldo": float(row.get('startsaldo', 0.0)),
                    "EndSaldo": float(row.get('endsaldo', 0.0)),
                    "Amount": amt,
                    "Category": cat,
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
                    "Account": "Trade Republic",
                    "StartSaldo": None,
                    "EndSaldo": None,
                    "Amount": amt,
                    "Category": cat,
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
tab_upload, tab_tx, tab_accounts, tab_budget, tab_analytics = st.tabs([
    "📥 Ingestion Hub", 
    "📝 Transactions", 
    "🏦 Accounts & Savings", 
    "⚖️ Zero-Based Planner", 
    "📊 Dashboard"
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
                    (df_transactions['Account'] == "Trade Republic") & 
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
                acc_txs = df_transactions[(df_transactions['Account'] == acc_num) & (df_transactions['Year'] == selected_year)].sort_values(by="Date")
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
        cash_txs = df_transactions[df_transactions['Category'] != 'Portfolio / Trading (Excluded)']
        
        total_income = cash_txs[cash_txs['Amount'] > 0]['Amount'].sum()
        total_transfers = abs(cash_txs[cash_txs['Category'] == 'Internal Savings / Transfer']['Amount'].sum())
        total_expenses = abs(cash_txs[(cash_txs['Amount'] < 0) & (cash_txs['Category'] != 'Internal Savings / Transfer')]['Amount'].sum())
        
        leftover = total_income - total_expenses - total_transfers
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Inflow", f"€{total_income:,.2f}")
        m2.metric("Living Expenses", f"€{total_expenses:,.2f}")
        m3.metric("Savings / Transfers", f"€{total_transfers:,.2f}")
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
        
        # Filter transactions for selected year
        df_year = df_transactions[df_transactions['Year'] == selected_dash_year].copy()
        
        # --- 1. WHERE DOES MY MONEY GO? (DONUT + TABLE) ---
        st.markdown("### **WHERE DOES MY MONEY GO?**")
        
        spend_df = df_year[
            (df_year['Amount'] < 0) & 
            (~df_year['Category'].isin(['Internal Savings / Transfer', 'Portfolio / Trading (Excluded)']))
        ].copy()
        spend_df['Expense_Amount'] = spend_df['Amount'].abs()
        
        if not spend_df.empty:
            breakdown_df = spend_df.groupby('Category')['Expense_Amount'].sum().reset_index()
            total_spend = breakdown_df['Expense_Amount'].sum()
            breakdown_df['%'] = (breakdown_df['Expense_Amount'] / total_spend * 100).round(2)
            breakdown_df = breakdown_df.sort_values(by='Expense_Amount', ascending=False)
            
            c1, c2 = st.columns([1, 1])
            with c1:
                fig_donut = px.pie(
                    breakdown_df, 
                    values='Expense_Amount', 
                    names='Category', 
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                fig_donut.update_layout(margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
                st.plotly_chart(fig_donut, use_container_width=True)
                
            with c2:
                display_table = breakdown_df.copy()
                display_table.columns = ['SUB-CATEGORY', 'AMOUNT', '%']
                display_table['AMOUNT'] = display_table['AMOUNT'].apply(lambda x: f"€ {x:,.2f}")
                display_table['%'] = display_table['%'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(display_table, hide_index=True, use_container_width=True)
        else:
            st.info("No spending transactions found for the selected year.")
            
        st.divider()
        
        # --- 2. ANNUAL INCOME VS EXPENSES ---
        st.markdown("### **ANNUAL INCOME vs EXPENSES**")
        
        months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Income monthly aggregation
        monthly_inc = df_year[df_year['Category'] == 'Income & Yield'].groupby('Month_Name')['Amount'].sum()
        
        # Expenses monthly aggregation
        monthly_exp = spend_df.groupby('Month_Name')['Expense_Amount'].sum()
        
        monthly_df = pd.DataFrame({'Income': monthly_inc, 'Expenses': monthly_exp}).reindex(months_order).fillna(0)
        
        fig_inc_exp = go.Figure()
        
        fig_inc_exp.add_trace(go.Bar(
            x=monthly_df.index,
            y=monthly_df['Expenses'],
            name='TOTAL EXPENSES',
            marker_color='#F7C59F'
        ))
        
        fig_inc_exp.add_trace(go.Scatter(
            x=monthly_df.index,
            y=monthly_df['Income'],
            name='INCOME',
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
        
        # --- 3. INVESTMENTS & SAVINGS OVER THE YEAR ---
        st.markdown("### **INVESTMENTS & SAVINGS TRACKER**")
        col_inv, col_sav = st.columns(2)
        
        # Investments
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
                
        # Savings
        sav_df = df_year[df_year['Category'] == 'Internal Savings / Transfer'].copy()
        sav_df['Amount'] = sav_df['Amount'].abs()
        
        with col_sav:
            st.markdown("**Monthly Savings / Transfers**")
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