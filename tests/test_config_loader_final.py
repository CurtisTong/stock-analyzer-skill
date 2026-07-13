import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestConfigLoaderMore:
    def test_safe_get_default(self):
        from config.loader import safe_get
        result = safe_get("nonexistent.yaml", "key", "default")
        assert result == "default"

    def test_safe_get_nested(self):
        from config.loader import safe_get
        result = safe_get("nonexistent.yaml", "a.b.c", 42)
        assert result == 42

    def test_safe_get_bool(self):
        from config.loader import safe_get
        result = safe_get("nonexistent.yaml", "enabled", True)
        assert result is True
