"""gate_channels.py: the 'locked until onboarded' permission plan."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_channels as gate  # noqa: E402

GUILD = "g1"
CREATORS = ["r_onboarded", "r_creator"]
STAFF = "r_staff"
ONBOARDING = "900"


def plan(channel, *, opening=False):
    return gate.plan_overwrites(channel, guild_id=GUILD, creator_role_ids=CREATORS,
                                staff_role_id=STAFF, onboarding_id=ONBOARDING, opening=opening)


def by_id(overwrites):
    return {o["id"]: (int(o["allow"]), int(o["deny"])) for o in overwrites}


def test_public_channel_is_hidden_from_everyone_and_opened_to_creators():
    out = by_id(plan({"id": "555", "name": "community-chat", "permission_overwrites": []}))
    assert out[GUILD] == (0, gate.VIEW_CHANNEL)            # @everyone can't see it
    for rid in CREATORS:
        assert out[rid] == (gate.VIEW_CHANNEL, 0)          # onboarded creators can
    assert out[STAFF] == (gate.VIEW_CHANNEL, 0)            # team never locked out


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
