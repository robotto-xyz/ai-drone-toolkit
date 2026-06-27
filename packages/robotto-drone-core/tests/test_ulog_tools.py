"""Tests for the ULog parsing layer, run against the official PX4 sample log.

Download the fixture once before running:
    make sample-log
    make test
"""

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


def test_missing_file_raises():
    with pytest.raises(ulog_tools.ULogError):
        ulog_tools.list_log_topics("/nope/does_not_exist.ulg")


def test_non_ulog_extension_raises(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("not a log")
    with pytest.raises(ulog_tools.ULogError):
        ulog_tools.get_log_summary(str(p))
