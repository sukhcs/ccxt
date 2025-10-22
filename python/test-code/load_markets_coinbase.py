import asyncio
import ccxt.async_support as ccxt

async def main():
    exchange = ccxt.coinbase()
    markets = await exchange.load_markets()  # ✅ Waits for result
    print(markets)
    await exchange.close()

asyncio.run(main())