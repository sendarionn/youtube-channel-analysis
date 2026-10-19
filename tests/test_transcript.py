import json

from ycanalysis.analyze.transcript import load_json3, speech_stats, text_between


def _write(tmp_path, events):
    p = tmp_path / "x.ja.json3"
    p.write_text(json.dumps({"events": events}))
    return p


def test_load_and_stats(tmp_path):
    p = _write(tmp_path, [
        {"tStartMs": 0, "dDurationMs": 5000, "segs": [{"utf8": "今日は少子化の話です"}]},
        {"tStartMs": 5000, "dDurationMs": 1000},  # segs なしは無視
        {"tStartMs": 100000, "dDurationMs": 5000, "segs": [{"utf8": "チャンネル登録お願いします"}]},
    ])
    segs = load_json3(p)
    assert len(segs) == 2
    assert text_between(segs, 0, 60) == "今日は少子化の話です"
    st = speech_stats(segs, duration=120)
    assert st["chars"] == len("今日は少子化の話です") + len("チャンネル登録お願いします")
    assert st["cta_subscribe"] == 1
    assert st["cta_in_last_60s"]
    assert not st["cta_in_first_60s"]


def test_first_time_across_segments():
    from ycanalysis.analyze.transcript import first_time
    segs = [{"start": 0.0, "end": 1, "text": "こんにちは"}, {"start": 3.0, "end": 4, "text": "海外ワ"},
            {"start": 4.0, "end": 5, "text": "イパです"}]
    assert first_time(segs, r"海外ワイパ") == 3.0
    assert first_time(segs, r"存在しない") is None
