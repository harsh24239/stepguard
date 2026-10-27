"""Check five visual part phrases through the SAM boundary; real mode by default.

No provider request format is defined here. All model calls stay in meta_client.
MOCK output requires explicit opt-in and never produces a go/no-go decision.
"""

import argparse
import json
from pathlib import Path
import sys

from backend import meta_client
from backend.inspector import InspectorConfig, decode_image, normalize_detection

MAX_IMAGE_BYTES = 10 * 1024 * 1024


class SAMCheckUnavailable(RuntimeError):
    """An adapter/contract failure is not evidence that the physical parts failed."""


def evaluate(image_bytes: bytes, phrases: list[str], *, allow_mock: bool = False) -> dict:
    phrases = [phrase.strip() for phrase in phrases]
    if len(phrases) != 5 or any(not phrase for phrase in phrases) or len({phrase.casefold() for phrase in phrases}) != 5:
        raise ValueError("Provide exactly five distinct, nonblank visual part phrases.")
    if meta_client.MOCK_MODE and not allow_mock:
        raise ValueError("M7 needs MOCK_MODE=false. Use --allow-mock only to exercise the script, not to evaluate SAM.")
    if not meta_client.MOCK_MODE and meta_client.MODEL_PROVIDER != "meta":
        raise ValueError("The M7 SAM gate requires MODEL_PROVIDER=meta. Gemini demo detections cannot establish a SAM result.")
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Use a nonempty overhead image of at most 10 MiB.")
    config = InspectorConfig()
    with decode_image(image_bytes, config) as image:
        size = image.size
    results = []
    for phrase in phrases:
        try:
            response = meta_client.segment(image_bytes, phrase)
        except NotImplementedError:
            raise SAMCheckUnavailable("The real SAM adapter is unavailable. Supply the official API documentation before running M7.") from None
        except Exception:
            # Adapter errors can include credentials, raw requests, or image bytes.
            raise SAMCheckUnavailable("The SAM call failed. No go/no-go decision was made; check the adapter and connection.") from None
        if not isinstance(response, list):
            raise SAMCheckUnavailable("SAM returned an invalid internal response. Fix the adapter contract before evaluating parts.")
        try:
            detections = [normalize_detection(item, phrase, size) for item in response]
        except Exception:
            raise SAMCheckUnavailable("SAM returned an invalid detection or mask. Fix the adapter contract before evaluating parts.") from None
        reliable = [item for item in detections if item.score >= config.min_score and item.area >= config.min_area_pixels]
        results.append({
            "phrase": phrase,
            "found": bool(reliable),
            "detection_count": len(detections),
            "reliable_detection_count": len(reliable),
            "mask_count": sum(bool(item.mask_png_base64) for item in detections),
            "scores": [item.score for item in detections],
        })
    found = sum(item["found"] for item in results)
    mock = meta_client.MOCK_MODE
    return {
        "mode": "MOCK" if mock else "LIVE",
        "image_size": list(size),
        "score_threshold": config.min_score,
        "min_area_pixels": config.min_area_pixels,
        "results": results,
        "found_phrases": found,
        "total_phrases": 5,
        "required_found_phrases": 4,
        "decision": "not_evaluated_mock" if mock else "go" if found >= 4 else "no_go",
        "note": ("Development fixture output only; the supplied image was not analyzed." if mock else
                 "Review detections against the photo. This threshold is a prototype gate, not an accuracy measurement."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="One overhead photo of the five distinct parts, preferably in private_assets/")
    parser.add_argument("--phrase", required=True, action="append", help="Visual noun phrase; repeat exactly five times")
    parser.add_argument("--allow-mock", action="store_true", help="Exercise fixtures only; never reports a real go/no-go")
    parser.add_argument("--report", type=Path, help="Optional JSON summary; keep private results in private_assets/")
    args = parser.parse_args(argv)
    try:
        # Reject this before making model calls as well as before writing a file.
        if args.report and args.report.resolve() == args.image.resolve():
            raise ValueError("Choose a report path different from the input image.")
        with args.image.open("rb") as image:
            image_bytes = image.read(MAX_IMAGE_BYTES + 1)
        report = evaluate(image_bytes, args.phrase, allow_mock=args.allow_mock)
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.report:
            args.report.write_text(encoded)
    except (OSError, ValueError, SAMCheckUnavailable) as error:
        # Do not echo filenames/OS details that might include private input.
        message = "The image could not be read or the report could not be saved." if isinstance(error, OSError) else str(error)
        print(f"SAM check unavailable: {message}", file=sys.stderr)
        return 2
    print(encoded, end="")
    return 1 if report["decision"] == "no_go" else 0


if __name__ == "__main__":
    raise SystemExit(main())
