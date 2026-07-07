"""join_listener.py fleet logic: root derivation, brand discovery, token grouping."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import join_listener as jl  # noqa: E402


def make_brand(root, name, *, enabled=True, token="tok-" + "x", guild="g1", with_tick=True):
    profile = root / "profiles" / name
    (profile / "scripts").mkdir(parents=True)
    (profile / "config.yaml").write_text(yaml.safe_dump({"ace": {
        "brand_id": name,
        "discord": {"guild_id": guild},
        "onboarding": {"enabled": enabled},
    }}), encoding="utf-8")
    (profile / ".env").write_text(f"DISCORD_BOT_TOKEN={token}\n", encoding="utf-8")
    if with_tick:
        (profile / "scripts" / "ace-onboarding-tick.py").write_text("# tick", encoding="utf-8")
    return profile


def test_derive_root_from_profile_path(tmp_path):
    profile = tmp_path / "profiles" / "glow"
    profile.mkdir(parents=True)
    assert jl.derive_root(profile) == tmp_path.resolve()
    assert jl.derive_root(tmp_path / "standalone") == (tmp_path / "standalone").resolve()


def test_discover_only_enabled_and_fully_wired(tmp_path):
    make_brand(tmp_path, "glow", guild="g1", token="tok-a")
    make_brand(tmp_path, "dark", enabled=False, guild="g2", token="tok-b")     # switch off
    make_brand(tmp_path, "broken", guild="g3", token="tok-c", with_tick=False)  # no tick installed
    profile = make_brand(tmp_path, "notoken", guild="g4", token="tok-d")
    (profile / ".env").write_text("OTHER=1\n", encoding="utf-8")               # no bot token
    found = jl.discover(tmp_path)
    assert [(e["guild_id"], e["token"]) for e in found] == [("g1", "tok-a")]


def test_group_by_token_shares_one_connection_per_bot(tmp_path):
    entries = [
        {"profile": "/p/a", "guild_id": "g1", "token": "tok-shared"},
        {"profile": "/p/b", "guild_id": "g2", "token": "tok-shared"},   # same bot, two servers
        {"profile": "/p/c", "guild_id": "g3", "token": "tok-own"},
    ]
    grouped = jl.group_by_token(entries)
    assert grouped == {
        "tok-shared": {"g1": "/p/a", "g2": "/p/b"},
        "tok-own": {"g3": "/p/c"},
    }
