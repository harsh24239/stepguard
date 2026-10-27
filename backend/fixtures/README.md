These fixtures were authored for StepGuard during setup; they contain no third-party assets. They are loaded only when `MOCK_MODE=true` and do not inspect the supplied PDF, image, or audio.

The segmentation fixture describes a synthetic 640 × 480 scene. Boxes use pixel coordinates `[x_min, y_min, x_max, y_max]`. Masks are empty in M1; this fixture supports boxes only. Unknown part prompts return an empty list. The judge fixture deliberately returns `unsure` so it cannot be mistaken for a successful inspection.

M3 tests derive original full-frame grayscale and alpha PNG masks in memory from synthetic pixel patterns. The inspector uses their foreground area, centroid, and overlap, while the original JSON fixture continues to exercise the box fallback. No private assets are required for these tests.

Run `.venv/bin/python -m scripts.inspect_fixture --output private_assets/m3-inspection.png` from the repository root to generate an original synthetic scene and annotated output. The command requires mock mode and labels the summary `MOCK`; it is a development check, not a model or assembly evaluation.

M6 routes recorded clips through the transcription boundary. The fixture still returns `step done` for every accepted clip, including silence, and the UI labels it as mock output. It is not evidence of speech recognition. Audio upload validation checks size, MIME, and basic container signatures only; tests generate original WAV silence in memory.
