# plumcodesbybit

Agents de trade autónomos para a **Bybit** (perpétuos USDT), 24/7.
O "cérebro" de cada agent é um **LLM** que recebe um snapshot de mercado + a
posição atual e devolve uma decisão estruturada (`open_long`, `open_short`,
`close`, `hold`). A execução, o dimensionamento e os limites de risco são
**determinísticos** e vivem fora do LLM.

Providers de LLM (configuráveis global ou por agent):

| `provider` | Endpoint | Chave |
|-----------|----------|-------|
| `anthropic` (default) | Claude / Anthropic API | `ANTHROPIC_API_KEY` |
| `nvidia` | `integrate.api.nvidia.com` (compatível com OpenAI) | `NVIDIA_API_KEY` de <https://build.nvidia.com> |

Podes correr o **mesmo símbolo com providers diferentes** em paralelo para os
comparar (ver `btc-demo-nvidia` no `agents.example.yaml`).

Suporta em simultâneo:

| Conta | Endpoint | Chaves |
|-------|----------|--------|
| `demo` | Bybit **Demo Trading** (`api-demo.bybit.com`) | geradas em *Demo Trading → API* |
| `real` | Bybit mainnet (`api.bybit.com`) | de uma **subconta** dedicada, sem permissão de saque |

> ⚠️ **Aviso**: trading alavancado tem risco elevado de perda total. Este
> software é fornecido "as-is", sem garantias. Corre semanas em `demo` antes de
> sequer pensar em `real`. Nada aqui é aconselhamento financeiro.

## Arquitetura

```
web UI (FastAPI)  ──►  Supervisor  ──►  Agent (1 por símbolo/conta, loop assíncrono)
      │                      │              │
   configstore (SQLite)   RuntimeConfig     ├─ market_data → klines+ticker+indicadores (pybit)
   agents + flags globais  (flags live)     ├─ brain      → LLM decide (anthropic|nvidia), JSON validado
                                            ├─ risk       → guardrails: confiança mín., 1 posição, kill-switch
                                            └─ trader     → ordem de mercado + TP/SL  (dry-run por omissão)
                                          state (SQLite)  → log de decisões + PnL diário
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env                 # preenche as chaves
cp config/agents.example.yaml config/agents.yaml
```

### Chaves Bybit

- **Demo**: entra na conta Bybit → *Demo Trading* → cria API key. Permissões:
  *Contract → Orders & Positions*.
- **Real**: cria uma **subconta** (Bybit → Sub-accounts), gera nela uma API key
  com **apenas** *Contract → Orders & Positions*, **sem** *Withdraw*, e (ideal)
  restrita ao IP do servidor. Nunca uses a chave da conta principal.

### Flags de segurança (`.env`)

| Flag | Efeito |
|------|--------|
| `PLUMBYBIT_DRY_RUN=true` | (default) decide e regista, **não envia ordens** |
| `PLUMBYBIT_ALLOW_REAL=false` | (default) agents `real` ficam sempre em simulado |
| `PLUMBYBIT_MAX_DAILY_LOSS_USDT` | perda realizada diária que congela aberturas |

Ordens reais só saem com `PLUMBYBIT_DRY_RUN=false` **e** `PLUMBYBIT_ALLOW_REAL=true`.

## Verificar ligação

```bash
python -m scripts.check_connection
```

## Correr

### Web UI (recomendado) — painel totalmente configurável

```bash
plumbybit-web            # ou: python -m plumbybit.web.app
```

Abre `http://127.0.0.1:8080`. O painel permite, **em runtime e sem reiniciar**:

- ligar/desligar `dry_run` e `allow_real`, ajustar `max_daily_loss_usdt`
- escolher provider/modelo de LLM (global) — reinicia os agents automaticamente
- CRUD de agents (símbolo, conta, timeframe, leverage, TP/SL, provider/modelo…)
- start/stop de cada agent
- ver posições abertas (live), decisões, PnL diário e logs

A config passa a viver em SQLite (`data/plumbybit.db`), semeada a partir do
`config/agents.yaml` no primeiro arranque. Segredos (API keys) **só** no `.env`.

Autenticação: define `PLUMBYBIT_WEB_PASSWORD` (e `PLUMBYBIT_WEB_SECRET`). Sem
password o painel fica aberto — usa só em localhost.

### Só os agents (sem web)

```bash
python -m plumbybit
```

### Docker (24/7)

```bash
docker compose up -d --build
docker compose logs -f          # painel em http://127.0.0.1:8080
```

## Configurar agents

`config/agents.yaml` — `defaults:` aplica-se a todos; cada entrada em `agents:`
pode sobrepor qualquer campo. Campos principais: `symbol`, `account`,
`interval`, `poll_seconds`, `leverage`, `max_position_usdt`,
`take_profit_pct`, `stop_loss_pct`, `enabled`, `provider`, `model`.

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap / por fazer

- Trailing stop e gestão de posição parcial
- Métricas Prometheus + dashboard
- Backtest do prompt de decisão sobre histórico
- Webhook de alertas (Telegram) em cada fill
