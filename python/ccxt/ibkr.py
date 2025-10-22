import time
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.ticktype import TickTypeEnum
from ibapi.common import *
from ccxt.base.exchange import Exchange
from ccxt.abstract.ibkr import ImplicitAPI


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
