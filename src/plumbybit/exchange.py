"""Wrapper fino sobre a pybit HTTP para contas demo e real.

- account="demo"  -> pybit HTTP(demo=True)   (api-demo.bybit.com)
- account="real"  -> pybit HTTP()            (api.bybit.com, mainnet)

As chaves da conta real devem ser de uma SUBCONTA dedicada, sem permissao de saque.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pybit.unified_trading import HTTP
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Account, Settings
from .logging_conf import get_logger

log = get_logger(__name__)

_RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=15), reraise=True)


class BybitError(RuntimeError):
    pass


class Exchange:
    """Cliente Bybit para uma conta (demo ou real)."""

    def __init__(self, account: Account, api_key: str, api_secret: str):
        if not api_key or not api_secret:
            raise BybitError(f"Chaves em falta para a conta '{account}'. Preenche o .env.")
        self.account = account
        self._http = HTTP(
            demo=(account == "demo"),
            api_key=api_key,
            api_secret=api_secret,
        )

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _unwrap(resp: dict[str, Any]) -> Any:
        if resp.get("retCode") != 0:
            raise BybitError(f"{resp.get('retCode')}: {resp.get('retMsg')}")
        return resp.get("result", {})

    # -- market data ---------------------------------------------------
    @retry(**_RETRY)
    def klines(self, category: str, symbol: str, interval: str, limit: int = 200) -> list[list[str]]:
        res = self._unwrap(self._http.get_kline(category=category, symbol=symbol, interval=interval, limit=limit))
        # Bybit devolve do mais recente para o mais antigo; invertemos.
        return list(reversed(res.get("list", [])))

    @retry(**_RETRY)
    def ticker(self, category: str, symbol: str) -> dict[str, Any]:
        res = self._unwrap(self._http.get_tickers(category=category, symbol=symbol))
        rows = res.get("list", [])
        if not rows:
            raise BybitError(f"Sem ticker para {symbol}")
        return rows[0]

    @retry(**_RETRY)
    def instrument(self, category: str, symbol: str) -> dict[str, Any]:
        res = self._unwrap(self._http.get_instruments_info(category=category, symbol=symbol))
        return res.get("list", [{}])[0]

    # -- account -----------------------------------------------------
    @retry(**_RETRY)
    def positions(self, category: str, symbol: str | None = None) -> list[dict[str, Any]]:
        kw = {"category": category, "settleCoin": "USDT"} if symbol is None else {"category": category, "symbol": symbol}
        res = self._unwrap(self._http.get_positions(**kw))
        return res.get("list", [])

    @retry(**_RETRY)
    def wallet_usdt(self) -> float:
        res = self._unwrap(self._http.get_wallet_balance(accountType="UNIFIED", coin="USDT"))
        rows = res.get("list", [])
        if not rows:
            return 0.0
        for coin in rows[0].get("coin", []):
            if coin.get("coin") == "USDT":
                return float(coin.get("equity") or coin.get("walletBalance") or 0.0)
        return 0.0

    # -- trading ---------------------------------------------------
    @retry(**_RETRY)
    def set_leverage(self, category: str, symbol: str, leverage: int) -> None:
        try:
            self._http.set_leverage(
                category=category, symbol=symbol,
                buyLeverage=str(leverage), sellLeverage=str(leverage),
            )
        except Exception as exc:
            if "110043" in str(exc) or "not modified" in str(exc).lower():
                return
            raise

    @retry(**_RETRY)
    def place_market_order(
        self,
        category: str,
        symbol: str,
        side: str,
        qty: str,
        take_profit: str | None = None,
        stop_loss: str | None = None,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = dict(
            category=category, symbol=symbol, side=side, orderType="Market",
            qty=qty, reduceOnly=reduce_only,
        )
        if take_profit:
            params["takeProfit"] = take_profit
        if stop_loss:
            params["stopLoss"] = stop_loss
        return self._unwrap(self._http.place_order(**params))


@lru_cache(maxsize=2)
def get_exchange(account: Account) -> Exchange:
    s = Settings()  # type: ignore[call-arg]
    key, secret = s.credentials(account)
    return Exchange(account, key, secret)
