import json

from ycanalysis.analyze.wayback_parse import parse_count, parse_snapshot


def test_parse_count():
    assert parse_count("33.2k subscribers") == 33200
    assert parse_count("1,234 views") == 1234
    assert parse_count("1.3万人") == 13000
    assert parse_count("No views") == 0
    assert parse_count(None) is None


def test_parse_snapshot():
    data = {"contents": [{"richItemRenderer": {"content": {"videoRenderer": {
        "videoId": "abcdefghijk", "viewCountText": {"simpleText": "5.4k views"},
        "publishedTimeText": {"simpleText": "2 days ago"}}}}}]}
    html = ('<script>"content":"55.2K subscribers" "content":"251 videos"</script>'
            f"<script>var ytInitialData = {json.dumps(data)};</script>")
    p = parse_snapshot(html)
    assert p["subscribers"] == 55200
    assert p["video_count"] == 251
    assert p["videos"] == [{"video_id": "abcdefghijk", "views": 5400, "published_text": "2 days ago"}]


def test_parse_count_words_and_anomaly():
    import pandas as pd
    from ycanalysis.analyze.wayback_parse import flag_anomalies
    assert parse_count("368 thousand subscribers") == 368000
    assert parse_count("1.2 million subscribers") == 1200000
    h = pd.DataFrame({"snapshot_at": pd.date_range("2022-01-01", periods=4),
                      "subscribers": [100000, 43500, 162000, 170000]})
    assert flag_anomalies(h)["anomaly"].tolist() == [False, True, False, False]


def test_header_with_handle_preferred_over_featured_channel():
    html = ('"content":"‎⁨@main⁩ • ⁨1.07M subscribers⁩"'
            ' "content":"‎⁨@other⁩ • ⁨55.1K subscribers⁩"')
    assert parse_snapshot(html)["subscribers"] == 1070000
