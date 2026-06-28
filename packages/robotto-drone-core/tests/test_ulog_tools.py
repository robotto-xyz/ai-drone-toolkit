"""Tests for the ULog parsing layer, run against the official PX4 sample log.

Download the fixture once before running:
    make sample-log
    make test
"""

import json
import os

import pytest

from robotto_drone_core import ulog_tools

SAMPLE = os.path.join(os.path.dirname(__file__), "sample.ulg")
pytestmark = pytest.mark.skipif(
    not os.path.isfile(SAMPLE), reason="tests/sample.ulg not downloaded"
)


def test_list_log_topics():
    out = ulog_tools.list_log_topics(SAMPLE)
    assert out["num_topics"] == 15
    names = {t["name"] for t in out["topics"]}
    assert "vehicle_attitude" in names
    # every topic reports a non-negative sample count and a field list
    for t in out["topics"]:
        assert t["num_samples"] >= 0
        assert isinstance(t["fields"], list)


def test_get_log_summary():
    out = ulog_tools.get_log_summary(SAMPLE)
    assert out["hardware"] == "AUAV_X21"
    assert 68 < out["duration_s"] < 70
    # the sample log contains 4 "no barometer" ERR messages
    assert out["num_warnings_or_errors"] == 4
    assert all(e["level"] == "ERR" for e in out["warnings_and_errors"])


def test_query_topic_filters_decimates_and_returns_stats():
    out = ulog_tools.query_topic(
        SAMPLE,
        "vehicle_local_position",
        fields=["z"],
        start_s=10,
        end_s=12,
        max_samples=5,
    )

    assert out["topic"] == "vehicle_local_position"
    assert out["fields"] == ["z"]
    assert out["num_samples_total"] > out["num_samples_returned"]
    assert out["num_samples_returned"] <= 5
    assert out["decimated"] is True
    assert out["decimation_stride"] > 1
    assert set(out["stats"]["z"]) >= {"first", "last", "min", "max", "mean"}
    assert all(10 <= sample["t_s"] <= 12 for sample in out["samples"])
    assert all("z" in sample for sample in out["samples"])
    json.dumps(out)  # no numpy scalars or other non-JSON values leak out


def test_query_topic_accepts_single_field_name():
    out = ulog_tools.query_topic(
        SAMPLE,
        "vehicle_local_position",
        fields="z",
        start_s=10,
        end_s=10.5,
        max_samples=50,
    )

    assert out["fields"] == ["z"]
    assert out["num_samples_returned"] > 0


def test_query_topic_bad_topic_raises():
    with pytest.raises(ulog_tools.ULogError, match="Topic not found"):
        ulog_tools.query_topic(SAMPLE, "definitely_not_a_topic")


def test_query_topic_bad_field_raises():
    with pytest.raises(ulog_tools.ULogError, match="Field\\(s\\) not found"):
        ulog_tools.query_topic(
            SAMPLE,
            "vehicle_local_position",
            fields=["definitely_not_a_field"],
        )


def test_get_failsafe_events():
    out = ulog_tools.get_failsafe_events(SAMPLE)

    assert out["file"] == "sample.ulg"
    assert out["num_events"] == len(out["events"])
    assert out["events"] == sorted(out["events"], key=lambda event: event["t_s"])
    assert any(event["type"] == "arming_state" for event in out["events"])
    arming_event = next(event for event in out["events"] if event["type"] == "arming_state")
    assert arming_event["to"] == "INIT"
    assert isinstance(out["armed_intervals"], list)
    json.dumps(out)


def test_get_failsafe_events_missing_vehicle_status(monkeypatch):
    class FakeULog:
        def get_dataset(self, _name):
            raise KeyError("vehicle_status")

    monkeypatch.setattr(ulog_tools, "_safe_load", lambda *_args, **_kwargs: FakeULog())

    out = ulog_tools.get_failsafe_events(SAMPLE)
    assert out["num_events"] == 0
    assert out["events"] == []
    assert out["armed_intervals"] == []
    assert "vehicle_status" in out["note"]


def test_missing_file_raises():
    with pytest.raises(ulog_tools.ULogError):
        ulog_tools.list_log_topics("/nope/does_not_exist.ulg")


def test_non_ulog_extension_raises(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("not a log")
    with pytest.raises(ulog_tools.ULogError):
        ulog_tools.get_log_summary(str(p))
