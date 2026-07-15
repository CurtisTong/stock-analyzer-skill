import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCheckVersion:
    def test_matching(self, tmp_path):
        from dev.sync_version import check_version

        f = tmp_path / "test.py"
        f.write_text('__version__ = "1.5.0"')
        result = check_version(
            str(f),
            "1.5.0",
            [(r'__version__\s*=\s*"[\d.]+"', '__version__ = "{version}"')],
        )
        assert result is True

    def test_mismatch(self, tmp_path):
        from dev.sync_version import check_version

        f = tmp_path / "test.py"
        f.write_text('__version__ = "1.0.0"')
        result = check_version(
            str(f),
            "1.5.0",
            [(r'__version__\s*=\s*"[\d.]+"', '__version__ = "{version}"')],
        )
        assert result is False


class TestUpdateAll:
    def test_dry_run(self):
        from dev.sync_version import update_all

        result = update_all("1.5.0", dry_run=True)
        assert isinstance(result, list)


class TestCheckVersions:
    def test_returns_dict(self):
        from dev.sync_version import check_versions

        result = check_versions("1.5.0")
        assert isinstance(result, dict)
