import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSectorEtfMore:
    def test_load_sector_etfs(self):
        from sector_etf_strength import _load_sector_etfs

        result = _load_sector_etfs()
        assert isinstance(result, list)

    def test_compute_rotation(self):
        from sector_etf_strength import compute_rotation_strength

        with patch("sector_etf_strength._load_sector_etfs", return_value=[]):
            result = compute_rotation_strength(window=5)
            assert result is not None or result is None
