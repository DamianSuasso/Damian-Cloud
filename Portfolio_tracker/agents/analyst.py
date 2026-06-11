import os
import re
from google import genai
from google.genai import types
from utils.analyzer import PortfolioAnalyzer

class SentinelAnalyst:
    def __init__(self):
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
        Retrieves a complete portfolio net worth evaluation snapshot up to a specific historical date.
        Use this tool when the user explicitly asks what their balances or values looked like in the past.
        
        Args:
            date_string: The target date formatted precisely as a string: 'YYYY-MM-DD'.
        """
        try:
            snapshot = self.analyzer.get_portfolio_snapshot_on_date(date_string)
            return str(snapshot)
        except Exception as e:
            return f"Snapshot Extraction Error: {str(e)}"

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
        print("💡 Try asking: 'Show me my last 3 transactions' or 'What was my net worth on 2026-03-15?'\n")
        
        # Pull live cost basis calculations to feed into the core setup
        cost_basis = self.analyzer.calculate_cost_basis()
        actual_db_schema = self.get_database_schema()
        
        system_instruction = f"""
        You are 'Sentinel', an autonomous private asset intelligence agent with read-only database privileges.
        
        CRITICAL DATABASE BLUEPRINT:
        You have absolute access to the following actual tables and columns in the database. Do not guess table names:
        {actual_db_schema}
        
        Pre-computed live cost basis matrix for quick reference: {cost_basis}.
        
        Operation Rules:
        1. When detailed tracking questions, asset distributions, or transaction calculations are requested, call the `query_portfolio_database` function using the exact schema layouts provided above.
        2. Always search using uppercase ticker strings inside queries (e.g., WHERE asset = 'ETH' or WHERE symbol = 'ADA').
        3. If a query fails or tables are missing, explain the database schema layout directly to the user so they can adjust their query.
        4. Keep answers clear, highly accurate, and maintain a sharp, professional, intelligent tone.
        """
        
        # Instantiate chat context with functional tools registered directly
        chat = self.client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                tools=[self.query_portfolio_database, self.get_historical_snapshot]
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