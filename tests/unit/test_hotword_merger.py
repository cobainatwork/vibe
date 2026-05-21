from shared.hotword_merger import merge_hotwords, parse_csv

MAX = 200


def test_parse_csv_basic():
    assert parse_csv("a,b,c") == ["a", "b", "c"]
    assert parse_csv("") == []
    assert parse_csv(None) == []


def test_parse_csv_strips_whitespace_and_empties():
    assert parse_csv(" a , b ,,c ") == ["a", "b", "c"]


def test_merge_groups_and_request():
    groups = [["g1-a", "g1-b"], ["g2-a"]]
    per_request = ["req-a"]
    merged = merge_hotwords(groups, per_request, max_words=MAX)
    assert set(merged) == {"g1-a", "g1-b", "g2-a", "req-a"}


def test_merge_dedupes_preserving_order():
    groups = [["a", "b", "c"]]
    per_request = ["b", "d", "a"]
    merged = merge_hotwords(groups, per_request, max_words=MAX)
    assert merged == ["a", "b", "c", "d"]


def test_merge_caps_at_max():
    groups = [[f"w{i}" for i in range(150)]]
    per_request = [f"r{i}" for i in range(100)]
    merged = merge_hotwords(groups, per_request, max_words=200)
    assert len(merged) == 200


def test_merge_empty_inputs():
    assert merge_hotwords([], [], max_words=MAX) == []
