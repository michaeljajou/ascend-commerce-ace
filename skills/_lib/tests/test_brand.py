"""_lib/brand.py: the brand's announcement target."""

from _lib import brand


def test_post_channel_is_the_first_post_behaviour_channel_by_name():
    cfg = {"discord": {"channels": {"community-chat": "FULL_ACTIVE", "challenges": "POST_ANSWER",
                                    "announcements": "POST_ONLY", "campaigns": "POST_ANSWER"}}}
    assert brand.post_channel(cfg) == "announcements"


def test_post_channel_is_none_without_a_post_behaviour_channel():
    assert brand.post_channel({"discord": {"channels": {"community-chat": "FULL_ACTIVE"}}}) is None
    assert brand.post_channel({}) is None
