# Session guardrails for brand Discord go-live

This reference captures the guardrail lessons from the July 2026 test-brand launch.

## What worked
- `display.tool_progress: 'off'` is important for creator-facing Discord bots.
- `GATEWAY_ALLOW_ALL_USERS=true` is a practical headless-VPS open-access toggle when you want the bot open to the server.
- `discord.free_response_channels` must be populated with numeric channel IDs or the bot may connect but remain silent in normal channels.
- `DISCORD_HOME_CHANNEL` + `DISCORD_HOME_CHANNEL_NAME` remove the noisy "No home channel is set" notice.

## What did not work well
- Long SOUL.md explanations were too weak; the model still replied helpfully to command / debug / authority prompts.
- Few-shot prefill priming was also too weak as a primary defense and should not be relied on for security behavior.
- Leaving terminal access in the brand's public Discord toolset is too much power for a chat-facing brand agent; prompt rules are not a security boundary.

## Better guardrail stack
1. Reduce tool surface first.
2. Keep `approvals.mode: smart`.
3. Keep `code_execution.mode: strict`.
4. Remove `terminal` from public Discord toolsets unless a brand truly needs it.
5. Keep SOUL.md short and flat: one exact rejection line for out-of-scope prompts.
6. Treat file-safety denials as defense-in-depth only; do not rely on them as the security boundary.

## Operational note
If a brand bot starts answering prompt-injection or debugging bait with explanations, tighten the toolset before making the prompt longer.
