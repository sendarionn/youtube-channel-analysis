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


def test_target_channel_node_excludes_recommended_channel():
    data = {"contents": [
        {"channelId": "UCother", "subscriberCountText": {"simpleText": "17.7K subscribers"}},
        {"channelId": "UCtarget", "subscriberCountText": {"simpleText": "251K subscribers"}},
    ]}
    html = f'<script>var ytInitialData = {json.dumps(data)};</script>'
    p = parse_snapshot(html, expected_channel_id="UCtarget")
    assert p["subscribers"] == 251000
    assert p["identity_validated"] is True
    assert p["subscriber_source"] == "channel_id_node"


def test_missing_target_does_not_fall_back_to_other_channel():
    data = {"channelId": "UCother", "subscriberCountText": {"simpleText": "17.7K subscribers"}}
    html = f'<script>var ytInitialData = {json.dumps(data)};</script>'
    assert parse_snapshot(html, expected_channel_id="UCtarget")["subscribers"] is None


def test_parse_count_additional_formats():
    assert parse_count("251K subscribers") == 251000
    assert parse_count("25.1万人") == 251000
    assert parse_count("251,000 subscribers") == 251000
    assert parse_count("1.07M subscribers") == 1070000
    assert parse_count("107万人") == 1070000


def _header_page(owner, header_handle, subs, featured=None):
    data = {"metadata": {"channelMetadataRenderer": {"externalId": owner}},
            "header": {"pageHeaderViewModel": {"metadata": {"rows": [
                {"text": {"content": header_handle}}, {"text": {"content": subs}}]}}},
            "contents": [featured or {}]}
    return f'<script>var ytInitialData = {json.dumps(data)};</script>'


def test_header_accepted_by_owner_id_even_if_handle_changed():
    p = parse_snapshot(_header_page("UCtarget", "@old_handle", "43.9k subscribers"),
                       expected_channel_id="UCtarget", expected_handle="@new_handle")
    assert p["subscribers"] == 43900 and p["subscriber_source"] == "page_owner_header"


def test_other_owner_page_is_rejected():
    p = parse_snapshot(_header_page("UCother", "@new_handle", "17.7K subscribers"),
                       expected_channel_id="UCtarget", expected_handle="@new_handle")
    assert p["subscribers"] is None


def test_unparseable_or_missing_subscribers_not_filled():
    p = parse_snapshot(_header_page("UCtarget", "@h", "no count here",
                                    {"channelId": "UCx", "subscriberCountText": {"simpleText": "9K subscribers"}}),
                       expected_channel_id="UCtarget")
    assert p["subscribers"] is None


def test_build_reparses_raw_and_audits_rejected_snapshots(tmp_path):
    from ycanalysis.analyze.wayback_parse import build
    (tmp_path / "20220101000000_channel.html").write_text(_header_page("UCtarget", "@h", "48.5K subscribers"))
    (tmp_path / "20220201000000_channel.html").write_text(_header_page("UCother", "@h", "1.75K subscribers"))
    (tmp_path / "20220301000000_channel.html").write_text(_header_page("UCtarget", "@h", "10K subscribers"))
    h, _, audit = build(tmp_path, "UCtarget", "@h", with_audit=True)
    assert h["subscribers"].tolist() == [48500, 10000]
    assert h["anomaly"].tolist() == [False, True]
    st = dict(zip(audit["file"].str[:8], audit["status"]))
    assert st == {"20220101": "有効", "20220201": "無効", "20220301": "疑義あり"}
    assert audit["note"][audit["status"] != "有効"].str.len().gt(0).all()
