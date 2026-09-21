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


def test_brand_assets_have_the_sizes_home_assistant_expects() -> None:
    from PIL import Image

    brand = COMPONENT / "brand"
    expected = {
        "icon.png": (256, 256),
        "icon@2x.png": (512, 512),
        "dark_icon.png": (256, 256),
        "dark_icon@2x.png": (512, 512),
        "logo.png": (317, 160),
        "logo@2x.png": (634, 320),
        "dark_logo.png": (317, 160),
        "dark_logo@2x.png": (634, 320),
    }
    for name, size in expected.items():
        with Image.open(brand / name) as image:
            assert image.size == size, name
            assert image.mode == "RGBA", name
