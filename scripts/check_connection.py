"""Verifica ligacao as contas Bybit e a chave Anthropic, sem enviar ordens.

    python -m scripts.check_connection
"""
from __future__ import annotations

import sys

from plumbybit.config import Settings, load_agents
from plumbybit.exchange import Exchange


def main() -> int:
    s = Settings()  # type: ignore[call-arg]
    ok = True

    for account in ("demo", "real"):
        key, secret = s.credentials(account)
        if not key or not secret:
            print(f"[{account}] sem chaves definidas - ignorado")
            continue
        try:
            ex = Exchange(account, key, secret)
            eq = ex.wallet_usdt()
            tk = ex.ticker("linear", "BTCUSDT")
            print(f"[{account}] OK - equity USDT={eq:.2f}, BTCUSDT last={tk.get('lastPrice')}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"[{account}] FALHOU: {exc}")

    try:
        agents = load_agents(s.agents_config)
        print(f"[config] {len(agents)} agents: {[a.name for a in agents]}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[config] FALHOU: {exc}")

    print(f"[flags] dry_run={s.dry_run} allow_real={s.allow_real} real_armed={s.real_trading_armed()}")
    print(f"[anthropic] key {'definida' if s.anthropic_api_key else 'EM FALTA'}, modelo={s.llm_model}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
