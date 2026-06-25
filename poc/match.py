"""Match Apple Photos against Google Photos by filename + date."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from apple_photos import ApplePhoto, build_lookup_key as apple_key
from google_photos import GooglePhoto, build_lookup_key as google_key


FUZZY_MINUTES = 2  # tolerance window for date matching


@dataclass
class MatchResult:
    google_photo: GooglePhoto
    apple_photo: Optional[ApplePhoto]
    confidence: str  # "high", "low", "unmatched"
    match_reason: str


def build_apple_index(apple_photos: list[ApplePhoto]) -> dict[str, ApplePhoto]:
    """Build filename+date lookup index from Apple Photos."""
    index = {}
    for photo in apple_photos:
        key = apple_key(photo.original_filename, photo.date)
        index[key] = photo
        # Also index by just filename as fallback
        base_key = apple_key(photo.original_filename, None)
        index.setdefault(f"filename_only:{base_key}", photo)
    return index


def match_photos(
    google_photos: list[GooglePhoto],
    apple_photos: list[ApplePhoto],
) -> list[MatchResult]:
    """Match each Google photo against Apple Photos library."""
    apple_index = build_apple_index(apple_photos)
    results = []

    for gp in google_photos:
        result = _match_single(gp, apple_index, apple_photos)
        results.append(result)

    return results


def _match_single(
    gp: GooglePhoto,
    apple_index: dict[str, ApplePhoto],
    apple_photos: list[ApplePhoto],
) -> MatchResult:
    # 1. Exact filename + date match (high confidence)
    key = google_key(gp.filename, gp.creation_time)
    if key in apple_index:
        return MatchResult(
            google_photo=gp,
            apple_photo=apple_index[key],
            confidence="high",
            match_reason="filename + date (exact)",
        )

    # 2. Fuzzy date match within tolerance window (low confidence)
    if gp.creation_time:
        for delta_minutes in range(1, FUZZY_MINUTES + 1):
            for sign in (1, -1):
                fuzzy_date = gp.creation_time + timedelta(minutes=delta_minutes * sign)
                fuzzy_key = google_key(gp.filename, fuzzy_date)
                if fuzzy_key in apple_index:
                    return MatchResult(
                        google_photo=gp,
                        apple_photo=apple_index[fuzzy_key],
                        confidence="low",
                        match_reason=f"filename + date (±{delta_minutes}min)",
                    )

    # 3. Filename-only match (low confidence)
    base_key = f"filename_only:{google_key(gp.filename, None)}"
    if base_key in apple_index:
        return MatchResult(
            google_photo=gp,
            apple_photo=apple_index[base_key],
            confidence="low",
            match_reason="filename only (no date match)",
        )

    # 4. No match found
    return MatchResult(
        google_photo=gp,
        apple_photo=None,
        confidence="unmatched",
        match_reason="no match found",
    )


def summarize(results: list[MatchResult]) -> dict:
    high = [r for r in results if r.confidence == "high"]
    low = [r for r in results if r.confidence == "low"]
    unmatched = [r for r in results if r.confidence == "unmatched"]
    return {
        "total_google": len(results),
        "high_confidence": len(high),
        "low_confidence": len(low),
        "unmatched": len(unmatched),
        "high": high,
        "low": low,
        "unmatched_list": unmatched,
    }
