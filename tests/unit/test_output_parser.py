from worker.output_parser import parse_transcription


def test_parse_well_formed_json():
    raw = (
        '[{"Start time":"0.00","End time":"2.50",'
        '"Speaker ID":"0","Content":"hi"}]'
    )
    segs = parse_transcription(raw)
    assert segs == [
        {"start_time": "0.00", "end_time": "2.50",
         "speaker_id": "0", "text": "hi"}
    ]


def test_parse_markdown_wrapped_json():
    raw = '```json\n[{"Start time":"1","End time":"2","Speaker ID":"0","Content":"x"}]\n```'
    segs = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["text"] == "x"


def test_parse_returns_empty_on_garbage():
    segs = parse_transcription("not json at all")
    assert segs == []


def test_parse_alternate_keys_normalized():
    # Some training outputs use shorter keys
    raw = '[{"Start":"0.0","End":"1.0","Speaker":"0","Content":"y"}]'
    segs = parse_transcription(raw)
    assert segs[0]["start_time"] == "0.0"
    assert segs[0]["speaker_id"] == "0"
