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


def test_base_role_gate_clears_everyone_and_grants_sight():
    """QA 2026-07-23: gated categories, yet a fresh join saw eleven channels — unsynced
    children don't inherit category overwrites; they fall back to the @everyone BASE
    role. The base role is the real gate. Other permission bits survive verbatim."""
    roles = [
        {"id": GUILD, "name": "@everyone", "permissions": str(gate.VIEW_CHANNEL | 2048)},
        {"id": "r_onboarded", "name": "onboarded", "permissions": "0"},
        {"id": "r_creator", "name": "creator", "permissions": str(gate.VIEW_CHANNEL)},
        {"id": STAFF, "name": "Ascend Team", "permissions": str(gate.ADMINISTRATOR)},
        {"id": BOT, "name": "Ace", "permissions": "0"},
    ]
    changes = gate.plan_role_permissions(roles, guild_id=GUILD, creator_role_ids=CREATORS,
                                         staff_role_id=STAFF, bot_role_id=BOT, opening=False)
    by_name = {c["name"]: c for c in changes}
    assert int(by_name["@everyone"]["permissions"]) == 2048        # view cleared, send kept
    assert int(by_name["onboarded"]["permissions"]) & gate.VIEW_CHANNEL
    assert int(by_name["Ace"]["permissions"]) & gate.VIEW_CHANNEL
    assert "creator" not in by_name                # already sighted — nothing to write
    assert "Ascend Team" not in by_name            # Administrator already implies sight
    assert list(by_name)[-1] == "@everyone"        # grants land before the lock


def test_base_role_gate_is_idempotent_and_open_restores():
    gated = [
        {"id": GUILD, "name": "@everyone", "permissions": "2048"},
        {"id": "r_onboarded", "name": "onboarded", "permissions": str(gate.VIEW_CHANNEL)},
        {"id": "r_creator", "name": "creator", "permissions": str(gate.VIEW_CHANNEL)},
        {"id": STAFF, "name": "s", "permissions": str(gate.VIEW_CHANNEL)},
        {"id": BOT, "name": "b", "permissions": str(gate.VIEW_CHANNEL)},
    ]
    common = dict(guild_id=GUILD, creator_role_ids=CREATORS, staff_role_id=STAFF,
                  bot_role_id=BOT)
    assert gate.plan_role_permissions(gated, opening=False, **common) == []
    restored = gate.plan_role_permissions(gated, opening=True, **common)
    assert [c["name"] for c in restored] == ["@everyone"]
    assert int(restored[0]["permissions"]) == 2048 | gate.VIEW_CHANNEL


def test_only_categories_and_orphans_are_written():
    """Categories + orphans get the tidy overwrites (role-scoped privacy, UI intent) —
    but they are belt, not gate: unsynced children don't inherit them, which is why
    the @everyone base role carries the actual lock."""
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


def test_home_channel_id_reads_env(tmp_path):
    """#agent-ace is team-facing (cron output, notifications): the gate excludes the
    creator-role allows there — an onboarded creator sees the community, not Ace's ops
    feed. The id comes from .env, where resolve_channels wrote it."""
    (tmp_path / ".env").write_text("X=1\nDISCORD_HOME_CHANNEL='1534255'\n", encoding="utf-8")
    assert gate.home_channel_id(tmp_path) == "1534255"
    assert gate.home_channel_id(tmp_path / "nope") is None
    ows = by_id(gate.plan_overwrites({"id": "1534255", "name": "agent-ace",
                                      "permission_overwrites": []},
                                     guild_id=GUILD, creator_role_ids=[],  # ops: no creators
                                     staff_role_id=STAFF, onboarding_id=ONBOARDING,
                                     opening=False, bot_role_id=BOT))
    assert ows[GUILD] == (0, gate.VIEW_CHANNEL)
    assert ows[STAFF] == (gate.VIEW_CHANNEL, 0) and ows[BOT] == (gate.VIEW_CHANNEL, 0)
    assert "r_onboarded" not in ows and "r_creator" not in ows


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


def test_already_private_categories_are_left_alone():
    """The gate narrows access; it must never widen it. A category that denies
    @everyone and does NOT allow creators (private 1:1 collab space) is skipped."""
    private_cat = {"id": "cat_paid", "type": 4, "name": "Paid Collab",
                   "permission_overwrites": [{"id": GUILD, "allow": "0",
                                              "deny": str(gate.VIEW_CHANNEL)}]}
    public_cat = {"id": "cat_text", "type": 4, "name": "Text Channels",
                  "permission_overwrites": []}
    already_gated = {"id": "cat_comm", "type": 4, "name": "Community",
                     "permission_overwrites": [
                         {"id": GUILD, "allow": "0", "deny": str(gate.VIEW_CHANNEL)},
                         {"id": CREATORS[0], "allow": str(gate.VIEW_CHANNEL), "deny": "0"}]}
    assert gate.is_already_private(private_cat, GUILD, CREATORS) is True
    assert gate.is_already_private(public_cat, GUILD, CREATORS) is False
    assert gate.is_already_private(already_gated, GUILD, CREATORS) is False  # ours, re-gate ok

    got = {c["id"] for c in gate.gate_targets(
        [private_cat, public_cat, already_gated], ONBOARDING,
        guild_id=GUILD, creator_role_ids=CREATORS)}
    assert got == {"cat_text", "cat_comm"}      # Paid Collab untouched
