#!/usr/bin/env python3
"""
Suggest custom themes based on patterns in photos
"""

import json
import re
from collections import defaultdict


def extract_keywords(filepath):
    """Extract potential keywords from filepath"""
    # Common activity keywords
    patterns = [
        r"judo",
        r"handball",
        r"soccer",
        r"football",
        r"birthday",
        r"christmas",
        r"holiday",
        r"vacation",
        r"trip",
        r"tournament",
        r"match",
        r"game",
        r"party",
        r"school",
        r"concert",
        r"recital",
    ]

    filepath_lower = filepath.lower()
    found = []
    for pattern in patterns:
        if re.search(pattern, filepath_lower):
            found.append(pattern)
    return found


def main():
    # Load metadata and clusters
    with open(".photobook-temp/metadata/photos_metadata.json", "r") as f:
        photos = json.load(f)

    # Analyze keywords
    keyword_photos = defaultdict(list)

    for photo in photos:
        filepath = f"{photo.get('Directory', '')}/{photo.get('FileName', '')}"
        keywords = extract_keywords(filepath)

        for keyword in keywords:
            keyword_photos[keyword].append(
                {
                    "filepath": filepath,
                    "date": photo.get("DateTimeOriginal") or photo.get("CreateDate"),
                }
            )

    # Find themes with multiple occurrences across different dates
    suggested_themes = []

    for keyword, photos_list in keyword_photos.items():
        if len(photos_list) >= 5:  # At least 5 photos
            # Check if spread across multiple dates
            dates = set()
            for p in photos_list:
                if p["date"]:
                    date_only = p["date"].split()[0]  # Get date part only
                    dates.add(date_only)

            if len(dates) >= 2:  # At least 2 different dates
                suggested_themes.append(
                    {
                        "theme_name": keyword.replace("_", " ").title(),
                        "keyword": keyword,
                        "photo_count": len(photos_list),
                        "date_count": len(dates),
                        "sample_photos": [p["filepath"] for p in photos_list[:5]],
                    }
                )

    # Sort by photo count
    suggested_themes.sort(key=lambda x: x["photo_count"], reverse=True)

    # Save suggestions
    with open(".photobook-temp/theme_suggestions.json", "w") as f:
        json.dump(suggested_themes, f, indent=2)

    print(f"Found {len(suggested_themes)} potential custom themes")
    print("Saved to .photobook-temp/theme_suggestions.json")


if __name__ == "__main__":
    main()
