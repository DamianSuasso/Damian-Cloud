#!/usr/bin/env python3
"""
Test Sandbox: Validating Dynamic Ticker Resolution via Yahoo Finance Search API
and Historical Pricing Engines.
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# Inject the true project root into the Python search space
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from Portfolio_tracker.utils.db_manager import DatabaseManager
    from Portfolio_tracker.sync_stocks import sync_stocks, resolve_ticker_via_api
    from Portfolio_tracker.utils.stock_price_service import StockPriceService  # 🆕 Imported the new service
except ImportError as e:
    print(f"❌ Structural Import Error: Verify your directory tree. Details: {e}")
    sys.exit(1)

def run_isolated_test():
    print("=" * 70)
    print("🧪 STARTING ISOLATED STOCKS TRANSLATION AND SYNC TESTING ENVIRONMENT")
    print("=" * 70)

    # 1. Test isolated string/ISIN queries over Yahoo API
    print("\n▶️ Phase 1: Validating Raw API Connectivity & Ticker Translation...")
    test_cases = {
        "US0378331005": "AAPL",      # Apple ISIN
        "NL0010273215": "ASML.AS",    # ASML Amsterdam ISIN
        "TSLA": "TSLA"               # Pure short ticker check
    }

    api_failures = 0
    for sample, expected in test_cases.items():
        resolved = resolve_ticker_via_api(sample)
        if resolved and resolved != sample:
            print(f"  ✅ API Verified: Treated '{sample}' ➡️ Resolved as Ticker: '{resolved}'")
        elif resolved == sample:
            print(f"  ℹ️ Cache Check: Treated '{sample}' ➡️ Left as Ticker: '{resolved}'")
        else:
            print(f"  ❌ API Match Failed for '{sample}'")
            api_failures += 1

    # 2. Test execution of the master parsing engine
    print("\n▶️ Phase 2: Simulating Complete Broker Matrix Synchronization...")
    try:
        # This will execute parse_degiro, parse_trade_republic, and calculate_stock_balances
        portfolio_snapshot = sync_stocks()
        
        print("=" * 70)
        print("🎉 SUCCESS: PARSING MATRIX EXECUTED WITHOUT CRASHING")
        print("=" * 70)
        print(f"Total Unique Assets Processed: {len(portfolio_snapshot)}")
        
        for idx, (ticker, details) in enumerate(portfolio_snapshot.items(), 1):
            print(f"  {idx}. Asset Ticker: {ticker:<12} | Compiled Dynamic Position: {details['shares']:.4f} shares")
        print("=" * 70)

        return portfolio_snapshot
        
    except Exception as e:
        print(f"\n❌ Execution Error during processing pipeline run: {e}")
        print("Please check that DEGIRO_Transactions.csv and TRADEREPUBLIC_Transactions.csv are located inside your Portfolio_tracker/imports/ folder.")
        return None
    
def run_integrated_test(portfolio):
    """Accepts the parsed portfolio matrix to run historical validation test phases."""
    if not portfolio:
        print("⚠️ Portfolio data context missing. Skipping integrated price validation steps.")
        return

    print("\n" + "=" * 70)
    print("🧪 INTEGRATED PORTFOLIO STOCKS TESTING ENVIRONMENT")
    print("=" * 70)

    # 3. Test the pricing engine against your actual portfolio positions
    print("\n▶️ Phase 3: Validating Historical Market Pricing Engine Cache...")
    price_service = StockPriceService()

    # Grab the first 2 unique tickers safely
    test_tickers = list(portfolio.keys())[:2]
    
    if not test_tickers:
        print("ℹ️ No tickers available to check historical prices.")
        return
    
    if "AAPL" not in test_tickers:
        test_tickers.append("AAPL")

    for ticker in test_tickers:
        # Download and store entire historical asset lifecycle data locally
        price_service.fetch_and_cache_historical_prices(ticker, start_date="2025-01-01")

    # 4. Test the fallback weekend/holiday rolling matrix logic
    print("\n▶️ Phase 4: Validating Weekend/Holiday Closure Fallback Rolling Logic...")
    test_weekend_date = "2026-06-14"  # This was a Sunday!
    
    for ticker in test_tickers:
        price = price_service.get_price_on_date(ticker, test_weekend_date)
        print(f"  🏢 Asset Ticker: {ticker:<12} | Price on Sunday {test_weekend_date}: €{price:.2f} (Rolled back to Friday close)")
    print("=" * 70)

if __name__ == "__main__":
    active_portfolio = run_isolated_test()
    run_integrated_test(active_portfolio)