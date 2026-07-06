# Prefill priming fallback

If a brand bot keeps answering in a helpful/debugging mode despite a short SOUL.md rejection,
use few-shot priming as a fallback — but only after the rejection pattern and classify-question
REJECT bucket are in place.

## Use case
- The model keeps giving partial explanations to command-like or authority-claim prompts.
- You need the bot to learn a very specific rejection shape.

## Pattern
Provide a small JSON array of alternating user/assistant messages that shows:
- several out-of-scope prompts
- the identical rejection line each time
- one legitimate brand question with a normal answer

## Caveat
Prefill priming is a behavior-shaping aid, not a security boundary. It should never be the only
control. Prefer approvals + script allowlists + prompt rules first.