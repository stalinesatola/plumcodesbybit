"""Entrypoint CLI: corre os agents sem web UI (`python -m plumbybit`).

A config vem do ConfigStore (SQLite), semeado a partir do agents.yaml no
primeiro arranque. Para editar em runtime, usa o web UI (`plumbybit-web`).
"""
from __future__ import annotations

import asyncio
import signal

from .logging_conf import configure, get_logger
from .supervisor import Supervisor

log = get_logger(__name__)


async def main() -> None:
    sup = Supervisor()
    configure(sup.settings.log_level)

    st = sup.runtime
    log.info("runner.start", dry_run=st.dry_run, real_armed=st.real_trading_armed(),
             agents=[a["name"] for a in sup.status() if a["enabled"]])

    await sup.start()
    if not sup._tasks:
        log.warning("nenhum agent ativo - edita a config pelo web UI ou pelo agents.yaml")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    await stop.wait()
    await sup.stop()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
