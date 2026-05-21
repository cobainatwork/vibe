"""Build prompts for VibeVoice ASR.

Byte-perfect aligned with upstream
vibevoice/processor/vibevoice_asr_processor.py:27, 360-364.
DO NOT modify the wording — the model was trained on this exact string.
"""

SYSTEM_PROMPT = (
    "You are a helpful assistant that transcribes audio "
    "input into text output in JSON format."
)

_SHOW_KEYS = ["Start time", "End time", "Speaker ID", "Content"]


def build_user_prompt(*, duration_sec: float, hotwords_csv: str) -> str:
    """Build the user-side prompt text.

    Args:
        duration_sec: audio duration in seconds (formatted to 2 decimals).
        hotwords_csv: comma-separated hotwords (already merged + capped),
                      empty string if none.
    """
    keys_str = ", ".join(_SHOW_KEYS)
    hw = hotwords_csv.strip() if hotwords_csv else ""
    if hw:
        return (
            f"This is a {duration_sec:.2f} seconds audio, "
            f"with extra info: {hw}\n\n"
            f"Please transcribe it with these keys: {keys_str}"
        )
    return (
        f"This is a {duration_sec:.2f} seconds audio, "
        f"please transcribe it with these keys: {keys_str}"
    )
