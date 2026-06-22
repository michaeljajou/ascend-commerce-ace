# Ace — Ascend Community Expert

A **Hermes skill bundle** that turns [Hermes](https://hermes-agent.nousresearch.com/docs) into
**Ace**, an always-on, multi-tenant AI support agent for Ascend Commerce's TikTok Shop creator
Discord communities. Ace answers *logistics* questions grounded in per-brand knowledge, **never
fabricates**, routes *content-strategy* questions to the human team, automates announcements,
moderates communities, and escalates to each brand's Slack channel.

This repo is **brand-agnostic** — it is the skill bundle only. Per-brand config and data live in
each Hermes **profile**, written there by the `setup-brand` skill. There is no orchestrator,
gateway, or messaging code here: Hermes provides all of that.

## How it fits together

| Layer | Owner |
|---|---|
| Container / runtime | **Hermes** (deployed via Hostinger one-click) |
| Discord + Slack gateways, agent loop, cron, profiles, models (OpenRouter) | **Hermes** |
| Behavior (classify, answer, escalate, moderate, announce, onboard…) | **this repo** — `skills/*` |
| Grounding & data (KB search, creator/deal lookup, ingest, digest) | **this repo** — skill scripts over a per-profile SQLite store |

Most skills are **instruction-only `SKILL.md`** (the Hermes agent reasons from them). Scripts exist
only for deterministic / grounding work (`ingest`, `search`, `deal`, `digest`, `setup`).

## Install (operator)

Hermes itself is provided by the Hostinger one-click deploy. Then, **once per Hermes deploy**:

```bash
# 1. install the skill bundle (Hermes CLI — NOT npx, NOT pip)
hermes skills install <this-repo>

# 2. only if Hermes does not auto-install declared skill deps:
uv pip install -r requirements-skills.txt
```

## Set up a brand (operator)

A skill runs *inside* a profile, so the profile must exist first:

```bash
# 3. create the brand's Hermes profile (attaches Discord bot token, Slack token, OpenRouter key/model)
hermes --profile <brand> setup        # exact command confirmed in Phase 0 spike

# 4. configure Ace inside that profile (channel scoping, Drive folder, Growi, crons, SOUL.md, first ingest)
/ace setup-brand
```

The brand team never touches Hermes — they keep their **Google Drive folder** current (brief, FAQ,
commission/payment, sample process, campaigns, paid-collab deals, compliance, onboarding guidance),
and a 24h cron (or `/ace update`) re-ingests it into that profile's store.

## Develop

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                 # core + eval-engine tests run on the stdlib (no extra installs)
```

## Evals (LLM-judged quality gate)

Two layers:

- **Offline gate** (`tests/evals/test_eval_gate.py`) — retrieval boundary using a deterministic
  fake embedder. Runs in `pytest` with zero installs, every time.
- **Live gate** (`tests/evals/`) — runs golden cases through a real model via OpenRouter, using the
  actual `SKILL.md` instruction bodies, with an **LLM judge** for grounding faithfulness. Three
  suites: `grounding` (never-fabricate), `classify` (HANDLE vs ROUTE), `moderation` (category).
  The engine is unit-tested offline with fake models; the live run needs a key:

```bash
OPENROUTER_API_KEY=sk-... python tests/evals/run.py     # exits non-zero if the gate fails
# optional overrides: ACE_EVAL_MODEL, ACE_JUDGE_MODEL, ACE_MIN_PASS_RATE
```

**Gate rule:** fails on any *critical* case (answering when it should escalate, a fabrication, or a
missed scam) and if any suite falls below the pass-rate floor (default 90%). Golden cases live in
`tests/evals/cases/*.jsonl` — add adversarial "almost-grounded" questions there to harden it.

## Layout

```
skills/            the product — one folder per skill (SKILL.md [+ scripts/] [+ tests/])
skills/_lib/       shared helpers (store, chunking, embeddings, drive, growi, models)
tests/                 cross-cutting only: golden eval gate + mocked end-to-end flows
```

See the full plan in `~/.claude/plans/attached-is-a-spec-giggly-penguin.md`.
