import os
import re
from google import genai
from google.genai import types
from Portfolio_tracker.utils.analyzer import PortfolioAnalyzer

class SentinelAnalyst:
    def __init__(self, historical_data=None):
        self.historical_data = historical_data or []
        self.client = genai.Client()
        self.analyzer = PortfolioAnalyzer()

    def query_portfolio_database(self, sql_query: str) -> str:
        """
        Executes a read-only SQL SELECT query on the portfolio database tracking 
        historical transaction ledgers (e.g., bitvavo_history, trade_republic_history, etc.).
        Use this tool whenever the user asks for exact counts, historical trade logs, 
        specific asset lookups, or raw ledger filtering.
        
        Args:
            sql_query: A valid SQLite read-only SELECT statement. Force uppercase strings for tickers (e.g., 'BTC').
        Returns:
            A string block representation of matching database records or rows.
        """
        try:
            # 🔗 Pointing precisely to your analyzer's DatabaseManager connection:
            cursor = self.analyzer.db.conn.cursor()
            
            # Simple security check to guard against accidental destructive commands
            upper_query = sql_query.upper().strip()
            if not upper_query.startswith("SELECT") and not upper_query.startswith("PRAGMA"):
                return "Error: Only read-only SELECT queries are authorized for this agent interface."
                
            cursor.execute(sql_query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            if not rows:
                return "Query executed successfully, but returned 0 rows matching those criteria."
                
            # Zip column headers with matching row contents for structured LLM parsing
            result_map = [dict(zip(columns, row)) for row in rows]
            return str(result_map)
            
        except Exception as e:
            return f"SQL Execution Error: {str(e)}"

    def get_historical_snapshot(self, date_string: str) -> str:
        """
        Retrieves a complete, granular asset breakdown portfolio evaluation snapshot on a specific past date.
        Use this tool when the user asks for exact asset balances, specific token quantities, 
        or historical average cost bases (Avg Buy) for a single specific day in the past.
        
        Args:
            date_string: The target historical date formatted precisely as 'YYYY-MM-DD'.
        Returns:
            A string dictionary containing individual asset balances, historical purchase averages, 
            and profit metrics for that exact day.
        """
        try:
            # Enforce fetching the complete data structure from your single-pass calculator
            snapshot = self.analyzer.get_portfolio_snapshot_on_date(date_string)
            return str(snapshot)
        except Exception as e:
            return f"Snapshot Extraction Error: {str(e)}"
    
    def get_historical_timeline_window(self, start_date: str = None, end_date: str = None) -> str:
        """
        Retrieves serialized daily portfolio performance metrics across an active time window.
        Use this tool whenever the user requests performance tracking over a range of dates, 
        asks for net profit/ROI progressions, compares asset performances percentually over time,
        or demands an inspection of equity/cash trends.

        Args:
            start_date: Optional boundary string formatted as 'YYYY-MM-DD'.
            end_date: Optional boundary string formatted as 'YYYY-MM-DD'.
        """
        if not self.historical_data:
            return "No pre-compiled historical timeline is available in memory."
            
        filtered_timeline = []
        for point in self.historical_data:
            point_date = point['date']
            if start_date and point_date < start_date:
                continue
            if end_date and point_date > end_date:
                continue
            filtered_timeline.append(point)
            
        if not filtered_timeline:
            return f"No timeline data points found matching the requested window boundaries."
            
        # Protect context window length while giving full coverage
        if len(filtered_timeline) > 31:
            snippet = filtered_timeline[:5] + [{"...": f"Truncated {len(filtered_timeline)-10} active days..."}] + filtered_timeline[-5:]
            return str(snippet)
            
        return str(filtered_timeline)

    def get_database_schema(self) -> str:
        """Dynamically inspects the SQLite database to get actual table names and columns."""
        try:
            cursor = self.analyzer.db.conn.cursor()
            # 1. Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            schema_details = []
            for table_tuple in tables:
                table_name = table_tuple[0]
                # 2. Get column names for each table
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = [col[1] for col in cursor.fetchall()]
                schema_details.append(f"Table '{table_name}' has columns: {columns}")
                
            return "\n".join(schema_details)
        except Exception as e:
            return f"Could not map schema: {e}"
        
    def start_chat_loop(self):
        print("\n🤖 Sentinel AI Broker Engine is online. Ask me anything about your holdings or transaction records! (Type 'exit' to quit)")
        if self.historical_data:
            latest = self.historical_data[-1]
            print(f"📊 Current Net Worth: €{latest['total_portfolio_value_eur']:,} | Total Crypto Profit: €{latest['total_unrealized_profit_eur']:,} | Total ROI: {latest['roi_percentage']}%")
        print("💡 Try asking: 'Show my profit trajectory over the last month' or 'What was my net worth on 2026-03-15?'\n")
        
        # Pull live cost basis calculations to feed into the core setup
        cost_basis = self.analyzer.calculate_cost_basis()
        actual_db_schema = self.get_database_schema()

        macro_summary = "No timeline history loaded."
        if self.historical_data:
            first = self.historical_data[0]
            last = self.historical_data[-1]
            macro_summary = (
                f"Historical Range: {first['date']} to {last['date']}. "
                f"Initial value: €{first['total_portfolio_value_eur']}. "
                f"Current total net value: €{last['total_portfolio_value_eur']} (Capital Invested: €{last['total_invested_eur']}, Unrealized Profit: €{last['total_unrealized_profit_eur']}, ROI: {last['roi_percentage']}%)."
            )
        
        system_instruction = f"""
        You are 'Sentinel', an autonomous private asset intelligence agent with read-only database privileges.
        
        CRITICAL DATABASE BLUEPRINT:
        You have absolute access to the following actual tables and columns in the database. Do not guess table names:
        {actual_db_schema}
        
        Pre-computed live cost basis matrix for quick reference: {cost_basis}.
        
        MACRO TIMELINE SUMMARY REFERENCE:
        {macro_summary}
        
        Operation Rules:
        1. When detailed transaction log audits, specific raw order records, or transaction calculations are requested, call the `query_portfolio_database` function.
        2. Always search using uppercase ticker strings inside queries (e.g., WHERE asset = 'ETH' or WHERE symbol = 'ADA').
        3. YOU DO NOT LACK HISTORICAL DATA. For tracking historical asset holdings, performance percentages over time, token quantities, and shifting cost bases on past dates:
           - Call `get_historical_snapshot` to get a complete individual asset balance/cost basis breakdown for a single specific day.
           - Call `get_historical_timeline_window` to analyze macro performance trajectories or find the best-performing asset percentually over a range of dates.
        4. Note: Double-entry accounting is active. Stablecoins and cash (EUR) have a baseline price of 1.0 and do not bloat invested crypto cost-basis allocations.
        5. Keep answers clear, highly accurate, and maintain a sharp, professional, intelligent tone.
        """
        
        # Instantiate chat context with functional tools registered directly
        chat = self.client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                # ☑️ CHANGED: Registered the new timeline window tool alongside the base functions
                tools=[self.query_portfolio_database, self.get_historical_snapshot, self.get_historical_timeline_window]
            )
        )
        
        while True:
            user_input = input("You 👤: ")
            if user_input.lower() in ['exit', 'quit']:
                print("Shutting down Sentinel Agent context. Keep tracking.")
                break
                
            if not user_input.strip():
                continue

            try:
                # The GenAI SDK automatically captures tool signatures, loops executions locally, 
                # and delivers the compiled answer string back seamlessly.
                response = chat.send_message(user_input)
                print(f"\nSentinel 🤖: {response.text}\n")
            except Exception as e:
                print(f"\nSentinel 🤖: System connection bottleneck: {e}\n")