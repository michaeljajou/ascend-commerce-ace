---
name: classify-question
description: Decide whether an incoming message is shop-operator scope (Ace handles) or creative-strategist scope (route to the human team).
version: 0.1.0
author: Ascend Commerce
license: MIT
---

# Classify Question

The behavioral boundary that gates every response. Decide which bucket a message falls into
**before** doing anything else. This is pure reasoning — no script.

## When to Use
Run first on any message Ace is allowed to act on (per the channel behavior map), in every
active channel including paid-collab and ambassador channels.

## Buckets
**HANDLE — shop-operator scope (Ace answers, grounded in the KB):**
- Sample shipping status & logistics; payment status & timing; commission rates & structure
- Collab progress (deadlines, deliverables, next steps); product info & sample requests
- Campaign / challenge logistics (how to participate, deadlines, prizes)
- Onboarding logistics; scheduling & timeline questions; general community support / FAQ

**ROUTE — creative-strategist scope (hand to the human team):**
- Content strategy or direction; feedback on a specific video or piece of content
- Hook frameworks / viral strategies; content format recommendations
- Coaching on making better content; creative-brief interpretation
- Any "what should I make" / "how should I film this" question

## Procedure
1. Read the message (plus recent channel context Hermes provides).
2. Pick exactly one: **HANDLE** or **ROUTE**.
3. On **HANDLE** → proceed to `answer-from-kb`.
4. On **ROUTE** → reply politely that the creative team will weigh in, then `escalate-to-team`
   with the reason `creative-strategist`.

## Pitfalls
- A logistics question *about* a content deal (e.g. "when is my video due?") is **HANDLE**, not ROUTE.
- When genuinely ambiguous, prefer **ROUTE** — never improvise content advice.
- Do not answer creative questions even if you "could"; that boundary is the point.

## Verification
- Logistics asks classify HANDLE; "what should I post?" classifies ROUTE.
- ROUTE always results in a polite hand-off + a team escalation, never a content opinion.
