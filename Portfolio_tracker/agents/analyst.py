import os
import re
from google import genai
from google.genai import types
from utils.analyzer import PortfolioAnalyzer

class SentinelAnalyst:
    def __init__(self):
        self.client = genai.Client()
        self.analyzer = PortfolioAnalyzer()

    def start_chat_loop(self):
        print("\n🤖 Sentinel AI Broker Engine is online. Ask me anything about your holdings or transaction records! (Type 'exit' to quit)")
        print("💡 Try asking: 'What is my current cost basis?' or 'What was my portfolio worth on 2026-03-01?'\n")
        
        # Pre-calculate data structures to supply as system context
        cost_basis = self.analyzer.calculate_cost_basis()
        
        # System instructions are now passed into a configuration object instead of an initial message
        system_instruction = f"""
        You are 'Sentinel', a private crypto intelligence agent. You have direct database access.
        Here is the user's computed live cost basis matrix: {cost_basis}.
        If the user asks about an exact historical date balance, ask them to wait while you interface with the database.
        Keep answers clear, highly accurate, short, and use a sharp, intelligent, professional tone.
        """
        
        # Open a stateful chat session using the newer, recommended mainline model
        chat = self.client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3
            )
        )
        
        while True:
            user_input = input("You 👤: ")
            if user_input.lower() in ['exit', 'quit']:
                print("Shutting down Sentinel Agent context. Keep tracking.")
                break
                
            # Intercept date queries dynamically so Python can calculate metrics safely
            if "worth on" in user_input.lower() or "balance on" in user_input.lower():
                print("🔍 Sentinel is extracting historical database blocks...")
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', user_input)
                if date_match:
                    target_date = date_match.group(0)
                    historical_snapshot = self.analyzer.get_portfolio_snapshot_on_date(target_date)
                    prompt = f"The user asked about their balances on {target_date}. The Python system queried the DB and returned this snapshot structure: {historical_snapshot}. Summarize this cleanly for them."
                else:
                    prompt = "The user asked about a past date, but no YYYY-MM-DD format was detected. Politely ask them to rephrase using YYYY-MM-DD format."
            else:
                prompt = user_input

            try:
                # The modern chat object uses send_message just like before, but routed through the new engine
                response = chat.send_message(prompt)
                print(f"\nSentinel 🤖: {response.text}\n")
            except Exception as e:
                print(f"\nSentinel 🤖: System connection bottleneck: {e}\n")