# Brand Discord security notes

## Guardrail hierarchy
1. Platform allowlist / channel scoping (usually SKIPPED for creator-facing bots — see below)
2. Approvals.mode = smart
3. Narrow command allowlist
4. Minimal tool surface — remove `terminal` from `platform_toolsets.<platform>` if the brand only needs approved scripts
5. Prompt rules and rejection patterns (SOUL.md OVERRIDE + classify-question REJECT)
6. Session hygiene — idle-based reset so old context can't be milked forever

## Important finding
Hermes file-tool read guards block `.env` and other credential files, but they are defense-in-depth only. The terminal tool runs as the same OS user and can bypass those guards. A profile boundary is organizational, not a hard security boundary.

## Practical implications
- A Discord-facing brand bot should not have arbitrary shell access if it is exposed to untrusted users. Prefer removing the `terminal` toolset entirely over relying on `approvals.mode` alone.
- `approvals.mode: off` is too permissive for a public brand bot.
- `code_execution.mode: strict` reduces risk by isolating `execute_code`.
- If full shell isolation is needed, use a separate OS user or container, not just a profile.

## Deliberate non-goal: user allowlisting
Some operators explicitly want the brand bot open to any Discord user (that's the point of a creator-support bot). Do NOT default to recommending `DISCORD_ALLOWED_USERS` or `require_mention: true` for this case — it defeats the bot's purpose. Instead push all the security weight onto layers 2-6 above (approvals, toolset, prompts, session hygiene). Only suggest allowlisting if the operator explicitly asks for a closed/private bot.

## Session poisoning — the most easily-missed failure mode
Prompt/config hardening (SOUL.md, classify-question, approvals) only changes what NEW sessions see. It does NOT retroactively scrub an EXISTING session's transcript. If a weaker earlier prompt let the model say something it shouldn't (e.g. paraphrase .env contents), that session will keep repeating/elaborating on the leak every time you re-test in it — even after every prompt fix lands — because the model is reading its own prior turn, not re-fetching the file.

Symptom to watch for: you tighten SOUL.md multiple times and the bot still produces the same leaked content nearly verbatim. This is NOT a sign the prompt hardening failed — check session history first.

Fix:
```
hermes --profile <brand> sessions list
hermes --profile <brand> sessions delete <session_id> --yes
```
Then re-test in a genuinely fresh session.

Prevention: set `session_reset.mode: idle` (with e.g. `idle_minutes: 60`) rather than `mode: none` for any brand profile facing real users, so stale/poisoned context can't accumulate indefinitely in a long-lived channel thread.

## Verification cues
- `hermes tools` / config should show `approvals.mode: smart`.
- `platform_toolsets.discord` (or equivalent) should NOT list `terminal` for a locked-down brand.
- Brand replies to out-of-scope prompts should be identical and short.
- Plain user questions in approved channels should work without needing broad user allowlists.
- `session_reset.mode` should be `idle` (or `both`), not `none`, for production brands.
