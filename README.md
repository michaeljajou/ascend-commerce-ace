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
| Grounding & data (knowledge lookup, creator/deal lookup, digest) | **this repo** — a per-brand knowledge YAML + a per-profile SQLite store |

Most skills are **instruction-only `SKILL.md`** (the Hermes agent reasons from them). Scripts exist
only for deterministic / grounding work (`get` knowledge, `deal` lookup, `digest`, `setup`).

Brand knowledge is a single structured **`knowledge.yaml`** the team maintains in the profile — read
live by `get-knowledge`, no ingestion/embeddings. The SQLite store holds only *operational* data
(creators, deals, interactions, feedback, moderation).

## Install (operator)

Hermes itself is provided by the Hostinger one-click deploy. Then, **once per Hermes deploy**, one command:

```bash
git clone <this-repo> ace && cd ace && ./install.sh
```

`./install.sh` registers this repo's `skills/` directory with Hermes as an **`external_dirs`** source
(in `~/.hermes/config.yaml`) and installs the script-only deps from `requirements-skills.txt`. Hermes
then discovers all skills **in place** — there's no per-skill copy, `skills/_lib` stays a sibling for
the scripts to import (Hermes ignores it as a skill since it starts with `_`), and **updates are just
`git pull`**. Keep the clone where it is — Hermes loads the skills from there.

Use `./install.sh --dry-run` to preview, `--no-deps` to skip the pip step, `--orchestrator <name>` to
target another orchestrator (when one's added).

> Why not `hermes skills install`? That command installs **one** skill at a time (from a tap/URL) and
> *copies* it into `~/.hermes/skills/` — it can't take a whole multi-skill repo, and it would strand
> our shared `skills/_lib`. `external_dirs` is Hermes' mechanism for loading your own skills directory.

## Set up a brand (operator)

A skill runs *inside* a profile, so the profile must exist first:

```bash
# 3. create the brand's Hermes profile (attaches Discord bot token, Slack token, OpenRouter key/model)
hermes --profile <brand> setup        # exact command confirmed in Phase 0 spike

# 4. configure Ace inside that profile (channel scoping, Growi, crons, SOUL.md) + drop in knowledge.yaml
/ace setup-brand
```

The brand team never touches Hermes — they keep the brand's **`knowledge.yaml`** current (brief, FAQ,
commission/payment, sample process, campaigns, compliance, onboarding guidance) in the profile. It's
read live by `get-knowledge`; edits take effect on the next read (no ingest/refresh).

## Develop

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"   # installs PyYAML (the one hard dep) + pytest
pytest
```

## Evals (LLM-judged quality gate)

Two layers:

- **Offline gate** (`tests/evals/test_eval_gate.py`) — the grounding boundary checked directly
  against the brand `knowledge.yaml` (no model): answerable questions resolve to knowledge,
  off-topic/creative ones resolve to nothing. Runs in `pytest` every time.
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
skills/_lib/       shared helpers (store, knowledge, moderation, growi, models, log_cli)
tests/                 cross-cutting only: golden eval gate + mocked end-to-end flows
```

See the full plan in `~/.claude/plans/attached-is-a-spec-giggly-penguin.md`.
