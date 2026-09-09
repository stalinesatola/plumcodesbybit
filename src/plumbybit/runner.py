"""Orquestrador: arranca todos os agents ativos em paralelo."""
from __future__ import annotations

import asyncio
import signal

from .agent import Agent
from .brain import Brain
from .config import Settings, load_agents
from .logging_conf import configure, get_logger
from .state import Store

log = get_logger(__name__)


async def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    configure(settings.log_level)

    agents_cfg = [a for a in load_agents(settings.agents_config) if a.enabled]
    if not agents_cfg:
        log.warning("nenhum agent ativo em %s", settings.agents_config)
        return

    real = [a.name for a in agents_cfg if a.account == "real"]
    log.info("runner.start",
             agents=[a.name for a in agents_cfg],
             dry_run=settings.dry_run,
             real_armed=settings.real_trading_armed(),
             real_agents=real)
    if real and not settings.real_trading_armed():
        log.warning("agents reais em modo simulado (PLUMBYBIT_ALLOW_REAL / PLUMBYBIT_DRY_RUN)", agents=real)

    store = Store(settings.state_db)
    brain = Brain(settings)
    tasks = [asyncio.create_task(Agent(c, settings, store, brain).run(), name=c.name) for c in agents_cfg]

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    await stop.wait()
    log.info("runner.stopping")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
