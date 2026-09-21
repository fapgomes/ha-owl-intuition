"""icons.json must only reference entities that exist in the translations."""
import json
from pathlib import Path

COMPONENT = Path(__file__).parent.parent / "custom_components" / "owl_intuition"


def test_icon_keys_match_translation_keys() -> None:
    icons = json.loads((COMPONENT / "icons.json").read_text())["entity"]
    names = json.loads((COMPONENT / "translations" / "en.json").read_text())["entity"]
    for platform, entries in icons.items():
        assert platform in names, platform
        for key, spec in entries.items():
            assert key in names[platform], f"{platform}.{key} has an icon but no name"
            assert spec["default"].startswith("mdi:"), f"{platform}.{key}"
