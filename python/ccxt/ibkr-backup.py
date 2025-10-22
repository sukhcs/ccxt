import time
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.ticktype import TickTypeEnum
from ibapi.common import *
from ccxt.base.exchange import Exchange
from ccxt.abstract.independentreserve import ImplicitAPI

class IBKRWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self._price_data = {}
        self._account_summary = {}
        self._positions = {}
        self._next_order_id = None

    def nextValidId(self, orderId: int):
        self._next_order_id = orderId

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType == TickTypeEnum.LAST or tickType == TickTypeEnum.CLOSE:
            self._price_data[reqId] = price

    def accountSummary(self, reqId, account, tag, value, currency):
        self._account_summary[tag] = value

    def position(self, account, contract, position, avgCost):
        self._positions[contract.symbol] = {
            "position": position,
            "avgCost": avgCost,
        }


class IBKRClient(EClient, IBKRWrapper):
    def __init__(self, host="127.0.0.1", port=7497, client_id=101):
        IBKRWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        if not self.isConnected():
            self.connect(host, port, client_id)
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            time.sleep(1)


# ---------------- CCXT subclass ------------------
class ibkr(Exchange, ImplicitAPI):
    """
    CCXT-compatible exchange class using Interactive Brokers API (ibapi).
    """

    def describe(self):
        return self.deep_extend(super().describe(), {
            'id': 'ibkr',
            'name': 'Interactive Brokers (IBAPI)',
            'countries': ['US'],
            'rateLimit': 2000,
            'has': {
                'fetchTicker': True,
                'fetchBalance': True,
                'createOrder': True,
                'fetchMarkets': True,
                'fetchOrder': True
            },
        })

    def __init__(self, config={}):
        super().__init__(config)

    def connect(self, config={}):
        print(f"Connecting to IBKR {self.id}")

        self.client = IBKRClient(
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 7497),
            client_id=config.get("client_id", 101),
        )

    def load_markets(self, reload=False, params={}):
        symbols = params.get("symbols", ["AAPL/USD", "MSFT/USD", "TSLA/USD"])
        markets = []
        for sym in symbols:
            base, quote = sym.split("/")
            markets.append({
                'id':      sym,      # string literal for referencing within an exchange
                'symbol':  sym,     # uppercase string literal of a pair of currencies
                'base':    base,         # uppercase string, unified base currency code, 3 or more letters
                'quote':   quote,         # uppercase string, unified quote currency code, 3 or more letters
                'baseId':  base,         # any string, exchange-specific base currency id
                'quoteId': quote,         # any string, exchange-specific quote currency id
                'active':   True,         # boolean, market status
                'type':    'spot',        # spot for spot, future for expiry futures, swap for perpetual swaps, 'option' for options
                'spot':     True,         # whether the market is a spot market
                'margin':   True,         # whether the market is a margin market
                'future':   False,        # whether the market is a expiring future
                'swap':     False,        # whether the market is a perpetual swap
                'option':   False,        # whether the market is an option contract
                'contract': False,        # whether the market is a future, a perpetual swap, or an option
                'settle':   'USDT',       # the unified currency code that the contract will settle in, only set if `contract` is true
                'settleId': 'usdt',       # the currencyId of that the contract will settle in, only set if `contract` is true
                'contractSize': 1,        # the size of one contract, only used if `contract` is true
                'linear':   True,         # the contract is a linear contract (settled in quote currency)
                'inverse':  False,        # the contract is an inverse contract (settled in base currency)
                'expiry':  1641370465121, # the unix expiry timestamp in milliseconds, undefined for everything except market['type'] `future`
                'expiryDatetime': '2022-03-26T00:00:00.000Z', # The datetime contract will in iso8601 format
                'strike': 4000,           # price at which a put or call option can be exercised
                'optionType': 'call',     # call or put string, call option represents an option with the right to buy and put an option with the right to sell
                # note, 'taker' and 'maker' compose extended data for markets, however it might be better to use `fetchTradingFees` for more accuracy
                'taker':    0.002,        # taker fee rate, 0.002 = 0.2%
                'maker':    0.0016,       # maker fee rate, 0.0016 = 0.16%
                'percentage': True,       # whether the taker and maker fee rate is a multiplier or a fixed flat amount
                'tierBased': False,       # whether the fee depends on your trading tier (your trading volume)
                'feeSide': 'get',         # string literal can be 'get', 'give', 'base', 'quote', 'other'
                'precision': {            # number of decimal digits "after the dot"
                    'price': 8,           # integer or float for TICK_SIZE roundingMode, might be missing if not supplied by the exchange
                    'amount': 8,          # integer, might be missing if not supplied by the exchange
                    'cost': 8,            # integer, very few exchanges actually have it
                },
                'limits': {               # value limits when placing orders on this market
                    'amount': {
                        'min': 0.01,      # order amount should be > min
                        'max': 1000,      # order amount should be < max
                    },
                    'price': { ... },     # same min/max limits for the price of the order
                    'cost':  { ... },     # same limits for order cost = price * amount
                    'leverage': { ... },  # same min/max limits for the leverage of the order
                },
                'marginModes': {
                    'cross': False,       # whether pair supports cross-margin trading
                    'isolated': False,    # whether pair supports isolated-margin trading
                },
                'info':      { ... },     # the original unparsed market info from the exchange
            })
        return markets

    # Helper: build IB contract
    def _make_contract(self, symbol, sec_type="STK", currency="USD", exchange="SMART"):
        c = Contract()
        c.symbol = symbol
        c.secType = sec_type
        c.currency = currency
        c.exchange = exchange
        return c

    # CCXT method: fetchMarkets
    def fetch_markets(self, params={}):
        symbols = params.get("symbols", ["AAPL/USD", "MSFT/USD", "TSLA/USD"])
        markets = []
        for sym in symbols:
            base, quote = sym.split("/")
            markets.append({
                'id':      sym,      # string literal for referencing within an exchange
                'symbol':  sym,     # uppercase string literal of a pair of currencies
                'base':    base,         # uppercase string, unified base currency code, 3 or more letters
                'quote':   quote,         # uppercase string, unified quote currency code, 3 or more letters
                'baseId':  base,         # any string, exchange-specific base currency id
                'quoteId': quote,         # any string, exchange-specific quote currency id
                'active':   True,         # boolean, market status
                'type':    'spot',        # spot for spot, future for expiry futures, swap for perpetual swaps, 'option' for options
                'spot':     True,         # whether the market is a spot market
                'margin':   True,         # whether the market is a margin market
                'future':   False,        # whether the market is a expiring future
                'swap':     False,        # whether the market is a perpetual swap
                'option':   False,        # whether the market is an option contract
                'contract': False,        # whether the market is a future, a perpetual swap, or an option
                'settle':   'USDT',       # the unified currency code that the contract will settle in, only set if `contract` is true
                'settleId': 'usdt',       # the currencyId of that the contract will settle in, only set if `contract` is true
                'contractSize': 1,        # the size of one contract, only used if `contract` is true
                'linear':   True,         # the contract is a linear contract (settled in quote currency)
                'inverse':  False,        # the contract is an inverse contract (settled in base currency)
                'expiry':  1641370465121, # the unix expiry timestamp in milliseconds, undefined for everything except market['type'] `future`
                'expiryDatetime': '2022-03-26T00:00:00.000Z', # The datetime contract will in iso8601 format
                'strike': 4000,           # price at which a put or call option can be exercised
                'optionType': 'call',     # call or put string, call option represents an option with the right to buy and put an option with the right to sell
                # note, 'taker' and 'maker' compose extended data for markets, however it might be better to use `fetchTradingFees` for more accuracy
                'taker':    0.002,        # taker fee rate, 0.002 = 0.2%
                'maker':    0.0016,       # maker fee rate, 0.0016 = 0.16%
                'percentage': True,       # whether the taker and maker fee rate is a multiplier or a fixed flat amount
                'tierBased': False,       # whether the fee depends on your trading tier (your trading volume)
                'feeSide': 'get',         # string literal can be 'get', 'give', 'base', 'quote', 'other'
                'precision': {            # number of decimal digits "after the dot"
                    'price': 8,           # integer or float for TICK_SIZE roundingMode, might be missing if not supplied by the exchange
                    'amount': 8,          # integer, might be missing if not supplied by the exchange
                    'cost': 8,            # integer, very few exchanges actually have it
                },
                'limits': {               # value limits when placing orders on this market
                    'amount': {
                        'min': 0.01,      # order amount should be > min
                        'max': 1000,      # order amount should be < max
                    },
                    'price': { ... },     # same min/max limits for the price of the order
                    'cost':  { ... },     # same limits for order cost = price * amount
                    'leverage': { ... },  # same min/max limits for the leverage of the order
                },
                'marginModes': {
                    'cross': False,       # whether pair supports cross-margin trading
                    'isolated': False,    # whether pair supports isolated-margin trading
                },
                'info':      { ... },     # the original unparsed market info from the exchange
            })
        return markets


    # CCXT method: fetchTicker
    def fetch_ticker(self, symbol, params={}):
        base, quote = symbol.split("/")
        contract = self._make_contract(base)
        req_id = 1001
        self.client.reqMktData(req_id, contract, "", False, False, [])
        time.sleep(2)
        price = self.client._price_data.get(req_id)
        self.client.cancelMktData(req_id)

        return {
            "symbol": symbol,
            "timestamp": self.milliseconds(),
            "datetime": self.iso8601(self.milliseconds()),
            "last": price,
            "info": {"source": "ibapi"},
        }

    # CCXT method: fetchBalance
    def fetch_balance(self, params={}):
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        time.sleep(2)
        self.client.cancelAccountSummary(9001)
        return {"info": self.client._account_summary}

    # CCXT method: createOrder
    def create_order(self, symbol, type, side, amount, price=None, params={}):
        contract = self._make_contract(symbol.split("/")[0])
        order = Order()
        order.action = side.upper()
        order.totalQuantity = amount
        order.orderType = "MKT" if type == "market" else "LMT"
        if order.orderType == "LMT" and price:
            order.lmtPrice = price

        # Wait for valid order ID
        while self.client._next_order_id is None:
            time.sleep(0.2)

        order_id = self.client._next_order_id
        self.client._next_order_id += 1
        self.client.placeOrder(order_id, contract, order)
        return {"id": order_id, "symbol": symbol, "side": side, "type": type}

    ## CUSTOM METHODS FOR FREQTRADE

    # CCXT method: fetchBalance
    def fetch_order(self, params={}):
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        time.sleep(2)
        self.client.cancelAccountSummary(9001)
        return {"info": self.client._account_summary}

    # CCXT method: fetchMyTrades
    def fetch_my_trades(self, params={}):
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        time.sleep(2)
        self.client.cancelAccountSummary(9001)
        return {"info": self.client._account_summary}

    # CCXT method: fetchBalance
    def fetch_tickers(self, params={}):
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        time.sleep(2)
        self.client.cancelAccountSummary(9001)
        return {"info": self.client._account_summary}

    # CCXT method: fetchBalance
    def watch_ohlc(self, params={}):
        self.client.reqAccountSummary(9001, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        time.sleep(2)
        self.client.cancelAccountSummary(9001)
        return {"info": self.client._account_summary}
