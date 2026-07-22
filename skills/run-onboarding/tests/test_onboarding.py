import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import assign_role  # noqa: E402
import onboarding  # noqa: E402

from _lib import sheet, store  # noqa: E402


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No Discord, no Slack, no profile config — the default for state-logic tests.

    Returns the recorder so a test can assert on what WOULD have been sent; the tests that
    care about the wire format re-patch the specific seam themselves.
    """
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(onboarding, "_post",
                        lambda text, key, default=None: sent.append((key, text)) or True)
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: {
                            "ok": True, "assigned": ["onboarded", "creator"]})
    monkeypatch.setattr(sheet, "brand_config", lambda profile=None: {})
    monkeypatch.setattr(sheet, "sync_creator", lambda row, **kw: False)
    return sent


def test_full_onboarding_flow(conn):
    onboarding.start(conn, "@ava", now=100.0)
    assert store.get_creator(conn, "@ava").onboarding_state == onboarding.COLLECTING

    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    out = onboarding.complete(conn, "@ava", role="creator", now=200.0)
    assert out["state"] == onboarding.COMPLETE

    c = store.get_creator(conn, "@ava")
    assert c.onboarding_state == "complete"
    assert c.role == "creator"
    assert c.last_active_at == "200.0"


def test_complete_requires_only_tiktok(conn):
    onboarding.start(conn, "@bo", now=100.0)
    with pytest.raises(ValueError):
        onboarding.complete(conn, "@bo")                      # no tiktok yet → blocked
    onboarding.set_fields(conn, "@bo", tiktok="bo.tt")
    out = onboarding.complete(conn, "@bo")                    # email/phone skipped → fine
    assert out["state"] == onboarding.COMPLETE


def test_phone_is_saved_and_optional(conn):
    onboarding.start(conn, "@po", now=100.0)
    out = onboarding.set_fields(conn, "@po", tiktok="po.tt", phone="+1 555 010 0100")
    assert out["phone"] == "+1 555 010 0100"
    assert onboarding.status(conn, "@po")["phone"] == "+1 555 010 0100"


def test_complete_unknown_creator_raises(conn):
    with pytest.raises(ValueError):
        onboarding.complete(conn, "@ghost")


def test_retry_counts_and_persists(conn):
    onboarding.start(conn, "@ava", now=100.0)
    assert onboarding.retry(conn, "@ava")["retries"] == 1
    assert onboarding.retry(conn, "@ava")["retries"] == 2
    assert onboarding.status(conn, "@ava")["retries"] == 2


def test_guided_starts_the_nudge_clock(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    onboarding.complete(conn, "@ava", now=200.0)
    out = onboarding.guided(conn, "@ava", now=300.0)
    assert out["state"] == "guided"
    row = onboarding.status(conn, "@ava")
    assert row["guided_at"] == "300.0"
    assert row["last_active_at"] is None      # engagement clock starts fresh


def test_reset_returns_to_start_keeping_identity(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", email="a@x.com")
    onboarding.complete(conn, "@ava")
    onboarding.guided(conn, "@ava", now=300.0)
    store.update_onboarding(conn, "@ava", discord_id="123", thread_id="th1", retries=2)
    out = onboarding.reset(conn, "@ava", now=400.0)
    assert out["reset"] is True
    row = onboarding.status(conn, "@ava")
    assert row["onboarding_state"] == "new"   # 'new' = the tick re-onboards with a fresh thread
    assert row["tiktok"] is None and row["email"] is None and row["retries"] == 0
    assert row["guided_at"] is None and row["nudged_at"] is None
    assert row["thread_id"] == "th1"          # kept so the tick can archive the old thread


def test_resolve_and_flag(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.flag(conn, "@ava")
    assert onboarding.status(conn, "@ava")["onboarding_state"] == "flagged"
    onboarding.resolve(conn, "@ava", now=500.0)
    row = onboarding.status(conn, "@ava")
    assert row["onboarding_state"] == "resolved" and row["resolved_at"] == "500.0"


def test_status_unknown_creator(conn):
    assert onboarding.status(conn, "@ghost")["error"] == "not found"


def test_stats_shape(conn):
    onboarding.start(conn, "@a", now=1.0)
    onboarding.retry(conn, "@a")
    store.update_onboarding(conn, "@a", onboarding_state="active", nudged_at="2.0")
    onboarding.start(conn, "@b", now=1.0)
    store.update_onboarding(conn, "@b", onboarding_state="active")
    s = store.onboarding_stats(conn)
    assert s["active_after_nudge"] == 1
    assert s["active_without_nudge"] == 1
    assert s["had_invalid_input"] == 1


def test_test_mode_toggle(tmp_path):
    import yaml
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ace": {"brand_id": "x"}}), encoding="utf-8")
    onboarding.set_test_mode(tmp_path, True)
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["ace"]["onboarding"]["test_mode"] is True
    assert cfg["ace"]["brand_id"] == "x"      # rest of config untouched
    onboarding.set_test_mode(tmp_path, False)
    assert yaml.safe_load((tmp_path / "config.yaml").read_text())["ace"]["onboarding"]["test_mode"] is False


def test_format_signup_shows_optional_gaps_explicitly():
    """A blank cell is ambiguous; '_not shared_' tells the team it was skipped."""
    text = onboarding.format_signup({
        "handle": "@ava", "tiktok": "ava.tt", "email": None, "phone": None,
        "discord_id": "77", "joined_at": "1784740716",
    })
    assert "New creator onboarded" in text and "@ava" in text
    assert "*ava.tt*" in text
    assert text.count("_not shared_") == 2          # email + phone
    assert "discord.com/users/77" in text


def test_complete_posts_to_slack_and_reports_it(conn, monkeypatch):
    from _lib import slack_cli

    posted = {}
    monkeypatch.undo()                                       # exercise the real _post
    monkeypatch.setattr(slack_cli, "main", lambda argv: posted.update(argv=argv) or 0)
    monkeypatch.setattr(sheet, "brand_config", lambda profile=None: {"onboarding": {}})
    monkeypatch.setattr(sheet, "sync_creator", lambda row, **kw: False)
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: {
                            "ok": True, "assigned": ["onboarded", "creator"]})

    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", phone="+1 555 010 0100")  # email skipped
    out = onboarding.complete(conn, "@ava", now=200.0)
    assert out["posted_to_slack"] is True
    assert "--channel" in posted["argv"]
    assert posted["argv"][posted["argv"].index("--channel") + 1] == "#ace-onboarding"
    body = posted["argv"][posted["argv"].index("--text") + 1]
    assert "ava.tt" in body and "+1 555 010 0100" in body and "_not shared_" in body


def test_slack_failure_never_blocks_completion(conn, monkeypatch):
    from _lib import slack_cli

    monkeypatch.undo()
    monkeypatch.setattr(slack_cli, "main", lambda argv: 1)       # Slack down
    monkeypatch.setattr(sheet, "brand_config", lambda profile=None: {"onboarding": {}})
    monkeypatch.setattr(sheet, "sync_creator", lambda row, **kw: False)
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: {
                            "ok": True, "assigned": ["onboarded", "creator"]})
    onboarding.start(conn, "@bo", now=100.0)
    onboarding.set_fields(conn, "@bo", tiktok="bo.tt")
    out = onboarding.complete(conn, "@bo", now=200.0)
    assert out["state"] == onboarding.COMPLETE                   # creator is still done
    assert out["posted_to_slack"] is False


def test_slack_exception_is_swallowed_not_raised(conn, monkeypatch):
    """QA regression: a Slack outage that raises must not take the creator down with it."""
    from _lib import slack_cli

    monkeypatch.undo()
    monkeypatch.setattr(sheet, "brand_config", lambda profile=None: {"onboarding": {}})
    monkeypatch.setattr(sheet, "sync_creator", lambda row, **kw: False)
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: {"ok": True, "assigned": ["creator"]})

    def boom(argv):
        raise OSError("network unreachable")

    monkeypatch.setattr(slack_cli, "main", boom)
    onboarding.start(conn, "@zo", now=100.0)
    onboarding.set_fields(conn, "@zo", tiktok="zo.tt")
    out = onboarding.complete(conn, "@zo", now=200.0)
    assert out["ok"] is True and out["posted_to_slack"] is False


# --- validation lives in the script, not the prompt ------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("ava.tt", "ava.tt"),
    ("@ava.tt", "ava.tt"),
    ("  @ava_tt  ", "ava_tt"),
    ("https://www.tiktok.com/@ava.tt", "ava.tt"),
    ("tiktok.com/@ava.tt", "ava.tt"),
    ("my tiktok is @ava.tt", "ava.tt"),          # creators answer in sentences
    ("it's @ava_tt!", "ava_tt"),
])
def test_tiktok_accepts_the_shapes_creators_actually_send(raw, expected):
    assert onboarding.normalize("tiktok", raw) == (expected, None)


@pytest.mark.parametrize("raw", [
    "my tiktok is coming soon",       # 'soon' matches the handle shape — must NOT be saved
    "my tiktok username is welcome-john-23",
    "@one and @two",                  # ambiguous: which did they mean?
])
def test_sentence_extraction_needs_an_unambiguous_at_tag(raw):
    assert onboarding.normalize("tiktok", raw) == (None, "not_a_handle")


@pytest.mark.parametrize("raw, reason", [
    ("welcome-john-2029", "not_a_handle"),   # the QA failure: a thread name, saved as a handle
    ("", "blank"),
    ("idk", None),                           # 'idk' IS a legal handle shape — we can't reject it
    ("a@b.com", "looks_like_email"),
    ("way_too_long_a_username_for_tiktok", "not_a_handle"),
    ("skip", "required"),                    # TikTok is the one field they can't skip
])
def test_tiktok_rejects_junk(raw, reason):
    value, got = onboarding.normalize("tiktok", raw)
    assert got == reason
    assert (value is None) == (reason is not None)


@pytest.mark.parametrize("word", ["skip", "no thanks", "Nope", "n/a", "rather not", "-"])
def test_declining_an_optional_field_is_not_an_error(word):
    assert onboarding.normalize("email", word) == ("", None)
    assert onboarding.normalize("phone", word) == ("", None)


def test_set_counts_a_retry_on_junk_and_saves_nothing(conn):
    onboarding.start(conn, "@ava", now=100.0)
    out = onboarding.set_fields(conn, "@ava", tiktok="welcome-john-2029")
    assert out == {"ok": False, "handle": "@ava", "field": "tiktok", "reason": "not_a_handle",
                   "retries": 1, "max_retries": 3, "limit_reached": False}
    assert onboarding.status(conn, "@ava")["tiktok"] is None


def test_set_flags_and_pages_the_team_once_patience_runs_out(conn, offline):
    onboarding.start(conn, "@ava", now=100.0)
    for _ in range(2):
        onboarding.set_fields(conn, "@ava", tiktok="!!!")
    out = onboarding.set_fields(conn, "@ava", tiktok="!!!")
    assert out["limit_reached"] is True
    assert out["state"] == "flagged"          # the script stops the loop itself
    assert out["team_notified"] is True
    assert any("can't get past" in text for _key, text in offline)


def test_skipping_an_optional_field_is_not_a_retry(conn):
    onboarding.start(conn, "@ava", now=100.0)
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt")
    out = onboarding.set_fields(conn, "@ava", email="skip")
    assert out["ok"] is True and out["skipped"] == ["email"]
    assert onboarding.status(conn, "@ava")["retries"] == 0


def test_answering_ace_counts_as_activity(conn):
    """Without this stamp the tick escalated creators who were mid-conversation."""
    onboarding.start(conn, "@ava", now=100.0)
    assert onboarding.status(conn, "@ava")["last_active_at"] is None
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt", now=500.0)
    assert onboarding.status(conn, "@ava")["last_active_at"] == "500.0"


# --- complete owns role assignment ------------------------------------------------------


def test_complete_assigns_roles_without_being_handed_an_id(conn, monkeypatch):
    """The agent should never have to find a Discord ID — that hunt is what broke QA."""
    seen = {}
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: seen.update(user_id=user_id)
                        or {"ok": True, "assigned": ["onboarded", "creator"]})
    onboarding.start(conn, "@ava", now=100.0)
    store.update_onboarding(conn, "@ava", discord_id="42")
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt")

    out = onboarding.complete(conn, "@ava", now=200.0)
    assert seen["user_id"] == "42"                     # pulled from the store, not the prompt
    assert out["ok"] is True and out["assigned"] == ["onboarded", "creator"]


def test_failed_role_assignment_blocks_completion_and_pages_the_team(conn, monkeypatch, offline):
    """With the access gate on, roles ARE server access: 'complete' while locked out is a lie."""
    monkeypatch.setattr(assign_role, "assign",
                        lambda user_id, roles=None, profile=None: {
                            "ok": False, "error": "HTTP 403: Missing Permissions"})
    onboarding.start(conn, "@ava", now=100.0)
    store.update_onboarding(conn, "@ava", discord_id="42")
    onboarding.set_fields(conn, "@ava", tiktok="ava.tt")

    out = onboarding.complete(conn, "@ava", now=200.0)
    assert out["ok"] is False and out["needs_team"] is True
    assert "Missing Permissions" in out["error"]
    assert out["team_notified"] is True
    assert onboarding.status(conn, "@ava")["onboarding_state"] != onboarding.COMPLETE
    assert any("role assignment failed" in text for _key, text in offline)


def test_missing_discord_id_is_a_clean_failure_not_a_crash(monkeypatch):
    monkeypatch.undo()                                 # exercise the real assign()
    out = assign_role.assign("")                       # no id on record
    assert out["ok"] is False and "Discord ID" in out["error"]
