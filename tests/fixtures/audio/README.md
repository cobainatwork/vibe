# Test Audio Fixtures

Place the following short audio files here (manual; not committed):

- `zh_tw_short.wav` (3-5s 繁中)
- `en_short.wav` (3-5s English)
- `mixed_short.wav` (3-5s 中英夾雜)
- `silent.wav` (< 0.5s for validation tests)
- `corrupted.mp3` (truncated bytes for decode failure tests)

These are excluded from git via `.gitignore`. Acquire from your
test corpus or generate with `ffmpeg`:

    ffmpeg -y -f lavfi -i sine=frequency=440:duration=3 tests/fixtures/audio/zh_tw_short.wav
