"""prep_server.py: the scripted half of new-server prep (roles, channels, intent check)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prep_server as prep  # noqa: E402


def test_plan_roles_creates_missing_and_flags_unmanageable():
    """Case-insensitive presence (operators type 'ascend team'; a case-twin duplicate
    would be worse than accepting theirs), and a role AT/ABOVE the bot's top role is
    reported for a human drag — Discord forbids the bot from managing it."""
    existing = [
        {"id": "e", "name": "@everyone", "position": 0},
        {"id": "1", "name": "ascend team", "position": 9},   # above bot_top=5
        {"id": "2", "name": "creator", "position": 2},
    ]
    plan = prep.plan_roles(existing, ["Ascend Team", "onboarded", "creator"], bot_top_position=5)
    assert plan["create"] == ["onboarded"]
    assert plan["present"] == ["ascend team", "creator"]
    assert plan["misplaced"] == ["ascend team"]


def test_plan_channels_ignores_non_text_namesakes_and_hash_prefixes():
    """A voice channel or category named like a wanted channel doesn't satisfy it, and
    operator input arrives '#'-prefixed straight from knowledge.yaml."""
    existing = [
        {"id": "1", "name": "community-chat", "type": 0},
        {"id": "2", "name": "campaigns", "type": 2},          # voice namesake
        {"id": "3", "name": "challenges", "type": 4},         # category namesake
    ]
    plan = prep.plan_channels(existing, ["#community-chat", "#campaigns", "challenges"])
    assert plan["create"] == ["campaigns", "challenges"]
    assert plan["present"] == ["community-chat"]


def test_intent_summary_accepts_limited_flags():
    """New brand bots are unverified, so Discord reports the *_LIMITED variant of each
    intent flag — that still means the portal toggle is ON and the intent works."""
    limited = (1 << 15) | (1 << 19)
    assert prep.intent_summary(limited) == {"server_members": True, "message_content": True}
    approved = (1 << 14) | (1 << 18)
    assert prep.intent_summary(approved) == {"server_members": True, "message_content": True}
    assert prep.intent_summary(0) == {"server_members": False, "message_content": False}


def test_reapply_is_a_no_op_plan():
    existing_roles = [{"id": str(i), "name": n, "position": 1}
                     for i, n in enumerate(["Ascend Team", "onboarded", "creator"])]
    existing_chans = [{"id": "9", "name": "agent-ace", "type": 0}]
    assert prep.plan_roles(existing_roles, prep.DEFAULT_ROLES, bot_top_position=5)["create"] == []
    assert prep.plan_channels(existing_chans, ["agent-ace"])["create"] == []
