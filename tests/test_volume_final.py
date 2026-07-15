import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestVolumeAnalysisMore:
    def test_empty(self):
        from technical.volume import volume_analysis

        result = volume_analysis([], [])
        assert result is None or isinstance(result, dict)

    def test_flat(self):
        from technical.volume import volume_analysis

        closes = [10.0] * 30
        volumes = [1000] * 30
        result = volume_analysis(closes, volumes)
        assert result is None or isinstance(result, dict)

    def test_increasing(self):
        from technical.volume import volume_analysis

        closes = [10 + i * 0.1 for i in range(30)]
        volumes = [1000 + i * 100 for i in range(30)]
        result = volume_analysis(closes, volumes)
        assert result is None or isinstance(result, dict)
