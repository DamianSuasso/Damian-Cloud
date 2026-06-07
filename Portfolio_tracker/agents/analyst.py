import os
import re
from google import genai
from google.genai import types
from utils.analyzer import PortfolioAnalyzer

class SentinelAnalyst:
    def __init__(self):
        self.client = genai.Client()
        self.analyzer = PortfolioAnalyzer()

    # 🛠️ Define the tools the model can execute. 
    # Type hinting and descriptive docstrings are mandatory; Gemini reads them to know how to use the tool!
    def query_portfolio_database(self, sql_query: str) -> str:
        """
        Executes a read-only SQL query on the user's portfolio database tracking 
        Bitvavo crypto exchanges, DEGIRO broker logs, Trade Republic transactions, and cold storage wallets.
        Use this tool whenever the user asks for exact amounts, trade counts, specific assets, 
        or raw transaction history across tables like bitvavo_history, cold_wallet_history, 
        degiro_history, and trade_republic_history.
        
        Args:
            sql_query: A valid SQLite read-only SELECT statement. Use UPPER() for coin/asset matches.
        Returns:
            A string representation of the rows returned by the database.
        """
        try:
            # We leverage the connection inside your existing analyzer framework
            cursor = self.analyzer.db_manager.conn.cursor()
            
            # Guard against dangerous statements
            upper_query = sql_query.upper().strip()
            if not upper_query.startswith("SELECT") and not upper_query.startswith("PRAGMA"):
                return "Error: Only read-only SELECT queries are authorized for this agent interface."
                
            cursor.execute(sql_query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            if not rows:
                return "Query executed successfully, but returned 0 rows matching those filters."
                
            # Format nicely as a structured block for the LLM to digest
            result_map = [dict(zip(columns, row)) for row in rows]
            return str(result_map)
            
        except Exception as e:
            return f"SQL Execution Error: {str(e)}"

    def get_historical_snapshot(self, date_string: str) -> str:
        """
        Retrieves a complete portfolio evaluation state on a specific historical date.
        Use this tool when the user explicitly asks how much their account was worth on a date, 
        or what their balances looked like in the past.
        
        Args:
            date_string: The target date formatted precisely as 'YYYY-MM-DD'.
        """
        try:
            snapshot = self.analyzer.get_portfolio_snapshot_on_date(date_string)
            return str(snapshot)
        except Exception as e:
            return f"Snapshot Extraction Error: {str(e)}"

    def start_chat_loop(self):
        print("\n🤖 Sentinel AI Broker Engine is online. Ask me anything about your holdings or transaction records! (Type 'exit' to quit)")
        print("💡 Try asking: 'Show me my last 3 buys for ETH' or 'How much ADA do I have in my cold storage wallet?'\n")
        
        # Calculate context layers for rapid identification
        cost_basis = self.analyzer.calculate_cost_basis()
        
        system_instruction = f"""
        You are 'Sentinel', an autonomous private asset intelligence agent. You have direct database read privileges.
        Here is the user's current basic live cost basis matrix: {cost_basis}.
        
        Rules:
        1. If you need precise data counts, historical timelines, transaction logs, or detailed asset totals, call the `query_portfolio_database` tool.
        2. Force string targets to uppercase inside queries (e.g., WHERE asset = 'ADA' or WHERE coin = 'ETH') to match layout conventions.
        3. Keep answers clear, highly accurate, short, and use a sharp, intelligent, professional tone.
        """
        
        # Register tools directly in the configuration architecture
        chat = self.client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                # Binding your functions into the executable workspace pipeline:
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
                # The GenAI SDK handles function execution routing automatically inside the chat session context
                response = chat.send_message(user_input)
                print(f"\nSentinel 🤖: {response.text}\n")
            except Exception as e:
                print(f"\nSentinel 🤖: System connection bottleneck: {e}\n")