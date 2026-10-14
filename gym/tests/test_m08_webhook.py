from pmg.m08_webhook import from_body


def test_parse_body():
    hook = from_body(b'{"url": "https://x.io", "secret": "s"}')
    assert hook.url == "https://x.io"
