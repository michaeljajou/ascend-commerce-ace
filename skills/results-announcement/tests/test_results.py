import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import results  # noqa: E402

PAYLOAD = {
    "campaign": "July GRWM Challenge",
    "winners": [
        {"handle": "@ava", "prize": "$500", "metric": "12 videos"},
        {"handle": "@bo", "prize": "$250"},
    ],
    "top_performers": [{"handle": "@cy"}, {"handle": "@di"}],
    "stats": {"videos": 120, "gmv": "$48k"},
}


def test_render_includes_campaign_winners_and_stats():
    text = results.render_payload(PAYLOAD)
    assert "July GRWM Challenge" in text
    assert "@ava" in text and "$500" in text and "12 videos" in text
    assert "Top performers" in text and "@cy" in text
    assert "videos: 120" in text


def test_render_handles_minimal_payload():
    text = results.render_payload({"name": "Mini"})
    assert "Mini" in text
    assert "participated" in text.lower()
