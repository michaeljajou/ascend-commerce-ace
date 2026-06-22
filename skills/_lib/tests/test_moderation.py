import pytest

from _lib import moderation as mod


def test_first_minor_issue_is_friendly():
    d = mod.resolve("negative_sentiment", prior_count=0)
    assert d.tier == mod.FRIENDLY
    assert d.notify_team is False


def test_second_issue_is_formal_and_notifies():
    d = mod.resolve("policy_violation", prior_count=1)
    assert d.tier == mod.FORMAL
    assert d.notify_team is True


def test_continued_violations_are_final():
    d = mod.resolve("policy_violation", prior_count=2)
    assert d.tier == mod.FINAL
    assert d.action == "timeout_delete_notify"


def test_scam_jumps_straight_to_final():
    d = mod.resolve("scam", prior_count=0)
    assert d.tier == mod.FINAL
    assert d.notify_team is True


def test_community_chat_negativity_redirects_to_thread():
    d = mod.resolve("negative_sentiment", prior_count=0, channel="community-chat")
    assert d.redirect_thread is True
    # not redirected elsewhere
    assert mod.resolve("negative_sentiment", prior_count=0, channel="dms").redirect_thread is False


def test_unknown_category_raises():
    with pytest.raises(ValueError):
        mod.resolve("vibes", prior_count=0)
