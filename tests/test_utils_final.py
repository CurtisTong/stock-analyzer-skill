import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestUtilsMore:
    def test_board_limit_pct(self):
        from common.utils import board_limit_pct, board_exact_limit_pct

        assert isinstance(board_limit_pct("主板"), float)
        assert isinstance(board_exact_limit_pct("主板"), float)

    def test_compute_optimal_workers(self):
        from common.utils import compute_optimal_workers

        assert isinstance(compute_optimal_workers(100), int)

    def test_batchify_more(self):
        from common.utils import batchify

        assert batchify([1, 2, 3], 1) == [[1], [2], [3]]
        assert batchify([], 5) == []

    def test_clamp_more(self):
        from common.utils import clamp

        assert clamp(50, 0, 100) == 50
        assert clamp(-1, 0, 100) == 0
        assert clamp(101, 0, 100) == 100

    def test_to_int_more(self):
        from common.utils import to_int

        assert to_int("42") == 42
        assert to_int(None) == 0
        assert to_int("abc") == 0
