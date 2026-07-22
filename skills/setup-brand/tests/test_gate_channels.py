"""gate_channels.py: the 'locked until onboarded' permission plan."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_channels as gate  # noqa: E402

GUILD = "g1"
CREATORS = ["r_onboarded", "r_creator"]
STAFF = "r_staff"
ONBOARDING = "900"


BOT = "r_bot"


def plan(channel, *, opening=False):
    return gate.plan_overwrites(channel, guild_id=GUILD, creator_role_ids=CREATORS,
                                staff_role_id=STAFF, onboarding_id=ONBOARDING, opening=opening,
                                bot_role_id=BOT)


def by_id(overwrites):
    return {o["id"]: (int(o["allow"]), int(o["deny"])) for o in overwrites}


def test_public_channel_is_hidden_from_everyone_and_opened_to_creators():
    out = by_id(plan({"id": "555", "name": "community-chat", "permission_overwrites": []}))
    assert out[GUILD] == (0, gate.VIEW_CHANNEL)            # @everyone can't see it
    for rid in CREATORS:
        assert out[rid] == (gate.VIEW_CHANNEL, 0)          # onboarded creators can
    assert out[STAFF] == (gate.VIEW_CHANNEL, 0)            # team never locked out
    assert out[BOT] == (gate.VIEW_CHANNEL, 0)              # Ace never locks itself out


def test_onboarding_channel_keeps_the_door_open():
    """New members must still see the onboarding channel — it's the only way in."""
    existing = [{"id": GUILD, "type": 0, "allow": "2048", "deny": "4096"}]   # send rules
    out = plan({"id": ONBOARDING, "name": "onboarding", "permission_overwrites": existing})
    everyone = next(o for o in out if o["id"] == GUILD)
    assert int(everyone["allow"]) & gate.VIEW_CHANNEL      # view added
    assert int(everyone["allow"]) & 2048                   # prior send-in-threads preserved
    assert int(everyone["deny"]) == 4096                   # prior deny preserved


def test_unrelated_overwrites_are_preserved():
    existing = [{"id": "some-mod-role", "type": 0, "allow": "8", "deny": "0"},
                {"id": GUILD, "type": 0, "allow": "1024", "deny": "0"}]
    out = plan({"id": "555", "name": "x", "permission_overwrites": existing})
    assert {"id": "some-mod-role", "type": 0, "allow": "8", "deny": "0"} in out
    assert by_id(out)[GUILD] == (0, gate.VIEW_CHANNEL)     # ours is replaced, theirs kept


def test_open_mode_restores_visibility_everywhere():
    out = by_id(plan({"id": "555", "name": "x", "permission_overwrites": []}, opening=True))
    assert out[GUILD] == (gate.VIEW_CHANNEL, 0)
    assert "r_creator" not in out                          # gate overwrites removed


def test_only_categories_and_orphans_are_written():
    """Children inherit their category — writing per-channel overwrites is redundant
    and is what produced a screen of 403s in QA."""
    channels = [
        {"id": "cat1", "type": 4, "name": "Text Channels"},
        {"id": "555", "type": 0, "name": "community-chat", "parent_id": "cat1"},
        {"id": "777", "type": 0, "name": "orphan"},
        {"id": ONBOARDING, "type": 0, "name": "onboarding"},
    ]
    got = {c["id"] for c in gate.gate_targets(channels, ONBOARDING)}
    assert got == {"cat1", "777", ONBOARDING}      # the child is left to inherit


def test_leaky_child_channels_are_detected():
    """A child that re-allows @everyone view defeats a gated category."""
    channels = [
        {"id": "555", "name": "leaky", "parent_id": "cat1",
         "permission_overwrites": [{"id": GUILD, "allow": str(gate.VIEW_CHANNEL), "deny": "0"}]},
        {"id": "556", "name": "fine", "parent_id": "cat1", "permission_overwrites": []},
        {"id": ONBOARDING, "name": "onboarding", "parent_id": "cat1",
         "permission_overwrites": [{"id": GUILD, "allow": str(gate.VIEW_CHANNEL), "deny": "0"}]},
    ]
    leaks = [c["name"] for c in gate.leaky_channels(channels, GUILD, ONBOARDING)]
    assert leaks == ["leaky"]                      # onboarding is meant to be open


def test_bot_allow_and_everyone_deny_land_in_one_patch():
    """On a fresh server the gate and the bot's own allow are written together, so the
    bot can never fence itself out of the category it just gated."""
    out = by_id(plan({"id": "cat1", "name": "Text Channels", "permission_overwrites": []}))
    assert out[GUILD] == (0, gate.VIEW_CHANNEL)
    assert out[BOT] == (gate.VIEW_CHANNEL, 0)          # same patch, no lockout window


def test_bot_granted_as_a_member_counts_as_allowed():
    """Operators often grant the bot USER directly rather than its role. A member-level
    overwrite is preserved by the plan and must satisfy the lockout guard too."""
    bot_member_overwrite = {"id": "bot-user-1", "type": 1,
                            "allow": str(gate.VIEW_CHANNEL), "deny": "0"}
    out = plan({"id": "cat1", "name": "Text Channels",
                "permission_overwrites": [bot_member_overwrite]})
    assert bot_member_overwrite in out          # kept verbatim, never stripped
