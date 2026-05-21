from worker.sse_parser import parse_sse_lines


def test_basic_content_event():
    lines = [
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
        '',
    ]
    events = list(parse_sse_lines(iter(lines)))
    assert len(events) == 1
    assert events[0].content == "hello"
    assert events[0].done is False


def test_done_marker():
    lines = ['data: [DONE]', '']
    events = list(parse_sse_lines(iter(lines)))
    assert len(events) == 1
    assert events[0].done is True


def test_skips_non_data_lines():
    lines = [
        ': keep-alive',
        'event: ping',
        'data: {"choices":[{"delta":{"content":"x"}}]}',
        '',
    ]
    events = list(parse_sse_lines(iter(lines)))
    assert len(events) == 1
    assert events[0].content == "x"


def test_handles_empty_delta():
    lines = ['data: {"choices":[{"delta":{}}]}']
    events = list(parse_sse_lines(iter(lines)))
    assert len(events) == 1
    assert events[0].content == ""


def test_malformed_json_skipped():
    lines = ['data: not-json', 'data: {"choices":[{"delta":{"content":"y"}}]}']
    events = list(parse_sse_lines(iter(lines)))
    assert len(events) == 1
    assert events[0].content == "y"
