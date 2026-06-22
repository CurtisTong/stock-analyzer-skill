"""common/version.py 版本管理测试。"""

import pytest
import re
from common.version import __version__


class TestVersion:
    """版本号规范。"""

    def test_version_exists(self):
        assert __version__ is not None

    def test_semver_format(self):
        """版本号遵循 SemVer 格式。"""
        pattern = r"^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$"
        assert re.match(pattern, __version__), f"Invalid version: {__version__}"

    def test_version_string(self):
        assert isinstance(__version__, str)

    def test_reasonable_version(self):
        """版本号主版本号在合理范围内。"""
        major = int(__version__.split(".")[0])
        assert 0 < major < 100
