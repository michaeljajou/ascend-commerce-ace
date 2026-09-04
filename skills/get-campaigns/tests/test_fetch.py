"""get-campaigns fetch.py: newest channel post = the active campaign/challenge."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch  # noqa: E402


def make_profile(tmp_path, channels=("campaigns", "challenges", "announcements")):
    (tmp_path / "channel_directory.json").write_text(json.dumps({
        "platforms": {"discord": [
            {"id": str(100 + i), "name": name, "type": "channel"}
            for i, name in enumerate(channels)
        ]}
    }), encoding="utf-8")
    (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=tok123\n", encoding="utf-8")
    return tmp_path


def msg(content, author="team", ts="2026-07-01T00:00:00Z", **extra):
    return {"content": content, "author": {"username": author}, "timestamp": ts, **extra}


def webhook_msg(content, ts, embeds=(), attachments=()):
    """A post made through a Discord webhook — how the I Am Joy team posts campaigns and
    announcements. Discord marks the author as a bot AND sets webhook_id."""
    return {
        "content": content,
        "author": {"username": "I Am Joy Brand", "bot": True, "id": "wh1"},
        "webhook_id": "wh1",
        "timestamp": ts,
        "embeds": list(embeds),
        "attachments": list(attachments),
    }


def test_summarize_newest_is_active_and_skips_empty():
    out = fetch.summarize([                       # Discord returns newest first
        msg("", ts="2026-07-06T00:00:00Z"),       # attachment-only → skipped
        msg("July Glow Challenge — post by 7/20, $500 prize", ts="2026-07-05T00:00:00Z"),
        msg("June campaign (over)", ts="2026-06-01T00:00:00Z"),
    ])
    assert out["active"]["content"].startswith("July Glow Challenge")
    assert [p["content"] for p in out["previous"]] == ["June campaign (over)"]


def test_summarize_empty_channel_means_no_active():
    assert fetch.summarize([]) == {"active": None, "previous": []}


def test_main_fetches_per_channel(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    calls = {}

    def fake_fetch(token, channel_id, limit):
        calls[channel_id] = (token, limit)
        return [msg(f"active in {channel_id}"), msg("older")]

    monkeypatch.setattr(fetch, "fetch_messages", fake_fetch)
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["channels"]["campaigns"]["active"]["content"] == "active in 100"
    assert out["channels"]["challenges"]["active"]["content"] == "active in 101"
    assert out["missing_channels"] == []
    assert calls["100"] == ("tok123", 10)          # token read from profile .env; default limit


def test_decorated_live_names_resolve(tmp_path, monkeypatch, capsys):
    """Live servers name these '🏁│campaigns' / '🏅│challenges'. Exact-name matching
    returned 'none of the channels exist', burned an onboarding run's whole iteration
    budget, and the exhaustion fallback leaked raw model markup into the creator's
    welcome thread (I Am Joy, 2026-08-04)."""
    make_profile(tmp_path, channels=("🏁│campaigns", "🏅│challenges", "📢│announcements"))
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(fetch, "fetch_messages", lambda *a: [msg("drop!")])
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing_channels"] == []
    assert out["channels"]["campaigns"]["active"]["content"] == "drop!"


def test_main_reports_missing_channels(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path, channels=("campaigns",))   # no #challenges / #announcements here
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(fetch, "fetch_messages", lambda *a: [msg("hi")])
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing_channels"] == ["challenges", "announcements"]


def test_main_errors_without_token(tmp_path, monkeypatch):
    make_profile(tmp_path)
    (tmp_path / ".env").write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 1


def test_main_errors_without_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 1


def test_summarize_skips_bot_authors():
    """Ace's own reply in the channel must never become the 'active' campaign."""
    out = fetch.summarize([
        {"content": "Love this! Happy to help!", "author": {"username": "ace", "bot": True},
         "timestamp": "2026-07-03T15:42:32Z"},
        msg("JUNE PERFORMANCE INCENTIVE CAMPAIGN", author="nimam_9", ts="2026-07-03T15:42:15Z"),
    ])
    assert out["active"]["content"] == "JUNE PERFORMANCE INCENTIVE CAMPAIGN"
    assert all("Love this" not in p["content"] for p in out["previous"])


# ── webhook posts + embeds (I Am Joy, 2026-08-28 / 2026-09-03) ─────────────────
# The team posts campaigns and announcements through a Discord webhook ("I Am Joy
# Brand"), with the text inside a rich embed. Discord flags webhook posts as bot-
# authored, and the old bot filter + empty-content filter dropped every one of them:
# #campaigns came back `active: null` on 2026-08-28 with the August monthly campaign
# live, and again on 2026-09-03 two hours after the September campaign was posted.
# Ace told two creators there was no active campaign.

def test_webhook_posts_are_team_posts():
    out = fetch.summarize([
        webhook_msg("🔥 MONTHLY CAMPAIGN IS LIVE — AUGUST 🔥 ...", ts="2026-08-03T20:37:31Z"),
    ])
    assert out["active"]["content"].startswith("🔥 MONTHLY CAMPAIGN IS LIVE")
    assert out["active"]["author"] == "I Am Joy Brand"


def test_non_webhook_bot_posts_are_still_skipped():
    out = fetch.summarize([
        {"content": "Happy to help!", "author": {"username": "ace", "bot": True},
         "timestamp": "2026-09-03T15:00:00Z"},
        webhook_msg("SEPTEMBER CAMPAIGN", ts="2026-09-03T13:50:13Z"),
    ])
    assert out["active"]["content"] == "SEPTEMBER CAMPAIGN"


def test_embed_text_is_part_of_the_post():
    """The September post's content was just '@everyone' — everything else was in the embed."""
    out = fetch.summarize([webhook_msg("@everyone", ts="2026-09-03T13:50:13Z", embeds=[{
        "type": "rich",
        "title": "🔥 MONTHLY CAMPAIGN IS LIVE — SEPTEMBER 🔥",
        "description": "A new month means a fresh chance to stack cash.",
        "fields": [
            {"name": "📅 CAMPAIGN DATES", "value": "**September 2nd → October 2nd**"},
            {"name": "🔗 REQUIRED TO QUALIFY", "value": "[JOIN](https://growi.io/o/x/c/54828)"},
        ],
        "footer": {"text": "Every video and every sale counts."},
    }])])
    text = out["active"]["content"]
    assert "MONTHLY CAMPAIGN IS LIVE — SEPTEMBER" in text
    assert "fresh chance to stack cash" in text
    assert "📅 CAMPAIGN DATES: **September 2nd → October 2nd**" in text
    assert "https://growi.io/o/x/c/54828" in text
    assert "Every video and every sale counts." in text


def test_embed_only_post_counts_as_text():
    out = fetch.summarize([webhook_msg("", ts="2026-07-06T18:58:55Z", embeds=[{
        "type": "rich", "title": "💰 FRESH CONTENT CHALLENGE — JULY 💰",
        "description": "Only GMV from videos posted THIS MONTH counts.",
    }])])
    assert out["active"]["content"].startswith("💰 FRESH CONTENT CHALLENGE — JULY 💰")


def test_link_preview_embeds_are_ignored():
    """Discord auto-attaches an 'article' unfurl for links in the text — the Growi site's
    tagline is not part of the campaign."""
    out = fetch.summarize([webhook_msg("Join here → https://growi.io/o/x/c/49051",
                                       ts="2026-08-03T20:37:31Z", embeds=[{
        "type": "article", "title": "AI discovery to payout, unified.",
        "description": "Growi is the all-in-one creator marketing platform.",
        "url": "https://growi.io/o/x/c/49051",
    }])])
    assert out["active"]["content"] == "Join here → https://growi.io/o/x/c/49051"


def test_image_only_post_is_skipped_but_attachments_are_listed():
    """A campaign graphic posted on its own has no readable text — the text post next to
    it stays active. Attachments on text posts are listed so Ace can point at them."""
    out = fetch.summarize([
        webhook_msg("", ts="2026-08-03T20:50:09Z",
                    attachments=[{"filename": "IAJB.png", "url": "https://cdn/IAJB.png"}]),
        webhook_msg("AUGUST CAMPAIGN", ts="2026-08-03T20:37:31Z",
                    attachments=[{"filename": "flyer.png", "url": "https://cdn/flyer.png"}]),
    ])
    assert out["active"]["content"] == "AUGUST CAMPAIGN"
    assert out["active"]["attachments"] == ["https://cdn/flyer.png"]
    assert out["previous"] == []


def test_announcements_is_a_mixed_feed_not_a_launch_channel():
    """The Growi 'Mega Campaign' (Aug 20 – Sep 20) lived only in #announcements, between a
    coaching-call notice and a leaderboard post. Newest-is-active does not apply there:
    every recent post is returned for Ace to scan."""
    out = fetch.summarize([
        webhook_msg("🔥 Top 5 creators this month by GMV are...", ts="2026-09-02T16:54:30Z"),
        webhook_msg("Weekly Coaching Call Update", ts="2026-09-01T14:18:35Z"),
        webhook_msg("🚀 MEGA CAMPAIGN — live until September 20", ts="2026-08-31T19:32:00Z"),
    ], mode="recent")
    assert "active" not in out
    assert [p["content"][:8] for p in out["recent"]] == ["🔥 Top 5 ", "Weekly C", "🚀 MEGA C"]


def test_main_reads_announcements_by_default(tmp_path, monkeypatch, capsys):
    make_profile(tmp_path)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(fetch, "fetch_messages",
                        lambda tok, cid, limit: [webhook_msg(f"post in {cid}", ts="2026-09-01T00:00:00Z")])
    assert fetch.main(["--profile-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["channels"]["announcements"]["recent"][0]["content"] == "post in 102"
    assert "active" not in out["channels"]["announcements"]
    assert out["channels"]["campaigns"]["active"]["content"] == "post in 100"
    assert out["fetched_at"]
