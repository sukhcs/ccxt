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
            },
        })

    def __init__(self, config={}):
        super().__init__(config)
        self.client = IBKRClient(
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 7497),
            client_id=config.get("client_id", 101),
        )

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
        # IB doesn't provide list of markets easily, so we define manually or via config
        symbols = params.get("symbols", ["AAPL/USD", "MSFT/USD", "TSLA/USD"])
        markets = []
        for sym in symbols:
            base, quote = sym.split("/")
            markets.append({
                "id": sym,
                "symbol": sym,
                "base": base,
                "quote": quote,
                "active": True,
                "type": "stock",
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
