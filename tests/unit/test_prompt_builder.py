from shared.prompt_builder import build_user_prompt, SYSTEM_PROMPT


def test_system_prompt_constant_matches_upstream():
    assert SYSTEM_PROMPT == (
        "You are a helpful assistant that transcribes audio "
        "input into text output in JSON format."
    )


def test_prompt_without_hotwords():
    p = build_user_prompt(duration_sec=351.73, hotwords_csv="")
    expected = (
        "This is a 351.73 seconds audio, please transcribe it with "
        "these keys: Start time, End time, Speaker ID, Content"
    )
    assert p == expected


def test_prompt_with_hotwords():
    p = build_user_prompt(duration_sec=120.50, hotwords_csv="微軟,VibeVoice")
    expected = (
        "This is a 120.50 seconds audio, with extra info: 微軟,VibeVoice\n\n"
        "Please transcribe it with these keys: Start time, End time, Speaker ID, Content"
    )
    assert p == expected


def test_prompt_strips_hotwords_whitespace():
    p = build_user_prompt(duration_sec=10.0, hotwords_csv="  a,b  ")
    assert "with extra info: a,b" in p


def test_duration_formatting_two_decimals():
    p = build_user_prompt(duration_sec=10, hotwords_csv="")
    assert "10.00 seconds" in p
