"""The debugging record has to survive the situations it exists to explain."""
import json
import sys
from pathlib import Path

import pytest

from _lib import trace


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    return tmp_path


def test_records_one_json_line_per_event(data_dir):
    trace.record("script.ok", command="onboarding.answer", handle="@ava", result={"ok": True})
    lines = (data_dir / trace.LOG_FILENAME).read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["command"] == "onboarding.answer" and entry["handle"] == "@ava"
    assert entry["python"] == sys.executable      # the field that would have caught PyYAML
    assert entry["ts"].startswith("20")


def test_invocation_times_a_successful_run(data_dir):
    with trace.Invocation("onboarding.status", handle="@ava") as run:
        run.result = {"state": "collecting"}
    entry = json.loads((data_dir / trace.LOG_FILENAME).read_text().splitlines()[-1])
    assert entry["event"] == "script.ok"
    assert entry["result"] == {"state": "collecting"}
    assert isinstance(entry["duration_s"], float)


def test_invocation_records_a_crash_and_re_raises_it(data_dir):
    with pytest.raises(ModuleNotFoundError):
        with trace.Invocation("onboarding.answer", handle="@ava"):
            raise ModuleNotFoundError("No module named 'yaml'")

    entry = json.loads((data_dir / trace.LOG_FILENAME).read_text().splitlines()[-1])
    assert entry["event"] == "script.error"
    assert "No module named 'yaml'" in entry["error"]
    assert "ModuleNotFoundError" in entry["traceback"]


def test_logging_never_breaks_the_caller(tmp_path, monkeypatch):
    """A creator's onboarding must not fail because a log file is unwritable."""
    monkeypatch.setenv("ACE_DATA_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    trace.record("script.ok", command="x")        # must not raise
    with trace.Invocation("y") as run:
        run.result = "fine"
    assert run.result == "fine"


def test_read_filters_by_handle(data_dir):
    trace.record("script.ok", command="a", handle="@ava")
    trace.record("script.ok", command="b", handle="@bo")
    trace.record("script.ok", command="c", handle="@ava")
    assert [e["command"] for e in trace.read("@ava")] == ["a", "c"]
    assert len(trace.read()) == 3


def test_read_survives_a_truncated_line(data_dir):
    trace.record("script.ok", command="a", handle="@ava")
    with (data_dir / trace.LOG_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write('{"partial": tru\n')          # a kill mid-write
    trace.record("script.ok", command="b", handle="@ava")
    assert [e["command"] for e in trace.read("@ava")] == ["a", "b"]


def test_render_shows_args_results_and_errors(data_dir):
    trace.record("script.ok", command="onboarding.answer", handle="@ava",
                 args={"text": ""}, result={"ok": False, "reason": "blank"}, duration_s=0.4)
    trace.record("script.error", command="onboarding.complete", handle="@ava",
                 error="ModuleNotFoundError: No module named 'yaml'", traceback="line\n")
    out = trace.render(trace.read("@ava"))
    assert '"text": ""' in out                    # the empty-message bug, visible at a glance
    assert '"reason": "blank"' in out
    assert "No module named 'yaml'" in out


def test_render_shows_fields_it_was_not_written_to_know_about(data_dir):
    """`answer.input` records where the creator's text came from — and the first version of
    render() silently dropped it, hiding the exact evidence it was added to capture."""
    trace.record("answer.input", handle="@ava", source="thread", text="bigjohn123",
                 thread_id="t1")
    out = trace.render(trace.read("@ava"))
    assert '"thread"' in out and "bigjohn123" in out and "t1" in out


def test_render_explains_an_empty_log_instead_of_printing_nothing(data_dir):
    assert "No trace events recorded" in trace.render([])
    assert str(data_dir) in trace.render([])


def test_rotation_caps_the_file_and_read_spans_both_generations(data_dir, monkeypatch):
    """The log must never fill a small VPS disk, so one generation is kept and older
    history is deliberately dropped — but a rotation must not blind `read` to the
    entries just before it."""
    for i in range(3):
        trace.record("script.ok", command=f"old{i}", handle="@ava")
    monkeypatch.setattr(trace, "MAX_BYTES", 1)          # next write rotates
    trace.record("script.ok", command="new0", handle="@ava")
    monkeypatch.setattr(trace, "MAX_BYTES", trace.MAX_BYTES * 10_000_000)
    trace.record("script.ok", command="new1", handle="@ava")

    assert (data_dir / (trace.LOG_FILENAME + ".1")).exists()
    commands = [e["command"] for e in trace.read("@ava")]
    assert commands == ["old0", "old1", "old2", "new0", "new1"]
