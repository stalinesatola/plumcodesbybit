# plumcodesbybit

Agents de trade autónomos para a **Bybit** (perpétuos USDT), 24/7.
O "cérebro" de cada agent é o **Claude** (Anthropic API): recebe um snapshot de
mercado + a posição atual e devolve uma decisão estruturada (`open_long`,
`open_short`, `close`, `hold`). A execução, o dimensionamento e os limites de
risco são **determinísticos** e vivem fora do LLM.

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
runner  ──►  Agent (1 por símbolo/conta, loop assíncrono)
                │
                ├─ market_data  →  klines + ticker + indicadores  (exchange/pybit)
                ├─ brain        →  Claude decide (structured output)
                ├─ risk         →  guardrails: confiança mín., 1 posição, kill-switch perda diária
                └─ trader       →  ordem de mercado + TP/SL   (dry-run por omissão)
              state (SQLite)    →  log de decisões + PnL diário
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

Local:

```bash
python -m plumbybit
```

Docker (24/7):

```bash
docker compose up -d --build
docker compose logs -f
```

## Configurar agents

`config/agents.yaml` — `defaults:` aplica-se a todos; cada entrada em `agents:`
pode sobrepor qualquer campo. Campos principais: `symbol`, `account`,
`interval`, `poll_seconds`, `leverage`, `max_position_usdt`,
`take_profit_pct`, `stop_loss_pct`, `enabled`.

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
