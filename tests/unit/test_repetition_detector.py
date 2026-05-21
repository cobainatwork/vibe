from worker.repetition_detector import RepetitionDetector


def test_no_loop_returns_no_repetition():
    d = RepetitionDetector(min_pattern_len=10, min_repeats=3, window_size=400)
    is_looping, _ = d.add_text("normal text without repetition")
    assert is_looping is False


def test_detects_repeated_long_pattern():
    d = RepetitionDetector(min_pattern_len=10, min_repeats=3, window_size=400)
    pattern = "abcdefghij"  # 10 chars
    text = pattern * 5
    d.text = text
    is_looping, _ = d._check_repetition()
    assert is_looping is True


def test_detects_repeated_phrase():
    d = RepetitionDetector(min_pattern_len=10, min_repeats=10, window_size=400)
    # 3 word phrase repeated 12 times
    d.text = "you are not " * 12
    is_looping, _ = d._check_repetition()
    assert is_looping is True


def test_reset_keeps_prefix():
    d = RepetitionDetector()
    d.text = "abc"
    d.reset(keep_text="abc")
    assert d.text == "abc"


def test_is_meaningful_filters_garbage():
    d = RepetitionDetector()
    assert d._is_meaningful("hello") is True
    assert d._is_meaningful("a") is False  # too few unique chars
    assert d._is_meaningful("  ") is False  # blank
