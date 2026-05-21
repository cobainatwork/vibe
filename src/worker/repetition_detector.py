"""Repetition detector — ported from upstream.

Source: vibevoice_src/vllm_plugin/tests/test_api_auto_recover.py:126-218
Do not modify the algorithm — upstream has tuned thresholds.
"""
from __future__ import annotations


class RepetitionDetector:
    """Detect repetition patterns in streaming text."""

    def __init__(
        self,
        min_pattern_len: int = 10,
        min_repeats: int = 3,
        window_size: int = 500,
    ):
        self.min_pattern_len = min_pattern_len
        self.min_repeats = min_repeats
        self.window_size = window_size
        self.text = ""

    def add_text(self, new_text: str) -> tuple[bool, int]:
        """Add new text, return (is_looping, good_text_end_pos)."""
        self.text += new_text
        return self._check_repetition()

    def _check_repetition(self) -> tuple[bool, int]:
        if len(self.text) < self.min_pattern_len * self.min_repeats:
            return False, len(self.text)

        window = (
            self.text[-self.window_size:]
            if len(self.text) > self.window_size
            else self.text
        )

        # Method 1: repeated substrings
        for pattern_len in range(self.min_pattern_len, len(window) // self.min_repeats + 1):
            pattern = window[-pattern_len:]
            count = 0
            pos = len(window)
            while pos >= pattern_len:
                if window[pos - pattern_len:pos] == pattern:
                    count += 1
                    pos -= pattern_len
                else:
                    break
            if count >= self.min_repeats:
                repetition_start = len(self.text) - (count * pattern_len)
                good_end = (
                    repetition_start + pattern_len
                    if self._is_meaningful(pattern)
                    else repetition_start
                )
                return True, good_end

        # Method 2: repeated short phrases
        words = window.split()
        if len(words) >= self.min_repeats * 2:
            for phrase_len in range(2, 6):
                if len(words) < phrase_len * self.min_repeats:
                    continue
                phrase = " ".join(words[-phrase_len:])
                count = 0
                idx = len(words)
                while idx >= phrase_len:
                    candidate = " ".join(words[idx - phrase_len:idx])
                    if candidate == phrase:
                        count += 1
                        idx -= phrase_len
                    else:
                        break
                if count >= self.min_repeats:
                    repeated_text = (phrase + " ") * count
                    good_end = (
                        len(self.text) - len(repeated_text.rstrip()) + len(phrase)
                    )
                    return True, max(0, good_end)

        return False, len(self.text)

    def _is_meaningful(self, pattern: str) -> bool:
        clean = pattern.strip()
        if not clean:
            return False
        if len(set(clean)) < 3:
            return False
        return True

    def reset(self, keep_text: str = "") -> None:
        self.text = keep_text
