"""统一版本号：所有 CLI 通过 --version 输出此版本。

P3: 从 pyproject.toml 动态读取，避免第四处硬编码（package.json/SKILL.md/
README 已由 sync_version.py 同步，version.py 此前未纳入）。
"""

import logging

logger = logging.getLogger(__name__)

try:
    from pathlib import Path


    def _read_version() -> str:
        try:
            root = Path(__file__).resolve().parents[2]
            pyproject = root / "pyproject.toml"
            if pyproject.exists():
                for line in pyproject.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("version"):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception as e:
            logger.debug("版本检查失败: %s", e)
        return "0.0.0"


    __version__ = _read_version()
except Exception:
    __version__ = "0.0.0"
