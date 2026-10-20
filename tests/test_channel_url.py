import pytest

from ycanalysis.channel_url import parse_channel_url


def test_japanese_encoded_handle():
    got = parse_channel_url("https://www.youtube.com/%40%E6%B5%B7%E5%A4%96Y%E3%83%91%E3%83%91")
    assert got.kind == "handle"
    assert got.value == "@海外Yパパ"
    assert got.canonical == "https://www.youtube.com/@海外Yパパ"


def test_channel_id():
    value = "UC1234567890abcdefghij"
    assert parse_channel_url(f"https://youtube.com/channel/{value}").value == value


@pytest.mark.parametrize("url", [
    "https://youtube.com/watch?v=abc",
    "https://youtube.com/playlist?list=abc",
    "https://example.com/@name",
])
def test_reject_non_channel_url(url):
    with pytest.raises(ValueError):
        parse_channel_url(url)
