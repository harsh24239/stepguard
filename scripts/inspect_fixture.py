"""Run M3 against the authored synthetic scene; this is a MOCK development check."""

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from backend import meta_client
from backend.inspector import inspect_step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional path for the annotated PNG")
    args = parser.parse_args()
    if not meta_client.MOCK_MODE:
        parser.error("This synthetic fixture check requires MOCK_MODE=true.")

    # The image and segmentation boxes describe the same original synthetic scene.
    fixtures = Path(__file__).resolve().parents[1] / "backend" / "fixtures"
    segments = json.loads((fixtures / "segments.json").read_text())
    step = json.loads((fixtures / "checklist.json").read_text())["steps"][1]
    image = Image.new("RGB", (640, 480), "#121a23")
    draw = ImageDraw.Draw(image)
    draw.text((12, 16), "MOCK - synthetic development fixture", fill="#e7bc72")
    for item in segments["yellow plate"]:
        draw.rectangle(item["box"], fill="#af982f")
    for item in segments["black pin"]:
        draw.ellipse(item["box"], fill="#13171c")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    result = inspect_step(step, image_bytes.getvalue())
    print(json.dumps({"mode": "MOCK", "synthetic_scene": True, **result.summary()}, indent=2))
    if args.output:
        args.output.write_bytes(result.annotated_image)


if __name__ == "__main__":
    main()
