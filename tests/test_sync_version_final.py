import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestGetPackageVersion:
    def test_returns_string(self):
        from dev.sync_version import get_package_version
        v = get_package_version()
        assert isinstance(v, str)


class TestResolveFiles:
    def test_python_file(self, tmp_path):
        from dev.sync_version import _resolve_files
        f = tmp_path / "test.py"
        f.write_text("")
        result = _resolve_files(str(f))
        assert len(result) >= 1


class TestApplyPatterns:
    def test_version_replacement(self):
        from dev.sync_version import _apply_patterns
        content = "version: 1.0.0"
        patterns = [(r"version:\s*([\d.]+)", "version: {version}")]
        result = _apply_patterns(content, "2.0.0", patterns)
        assert "2.0.0" in result


class TestUpdateVersion:
    def test_update(self, tmp_path):
        from dev.sync_version import update_version
        f = tmp_path / "test.py"
        f.write_text('__version__ = "1.0.0"')
        update_version(str(f), "2.0.0", [(r'__version__\s*=\s*"[\d.]+"', '__version__ = "{version}"')])
        assert "2.0.0" in f.read_text()
