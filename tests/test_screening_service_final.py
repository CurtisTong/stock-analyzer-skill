import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestBoardLimit:
    def test_main_board(self):
        from business.screening_service import _board_limit
        assert _board_limit("主板") == 9.5

    def test_gem(self):
        from business.screening_service import _board_limit
        assert _board_limit("创业板") == 19.5

    def test_star(self):
        from business.screening_service import _board_limit
        assert _board_limit("科创板") == 19.5


class TestMinSurvivalCap:
    def test_main(self):
        from business.screening_service import _min_survival_cap
        assert isinstance(_min_survival_cap("主板"), float)

    def test_other(self):
        from business.screening_service import _min_survival_cap
        assert isinstance(_min_survival_cap("其他"), float)


class TestThresholds:
    def test_goodwill(self):
        from business.screening_service import _goodwill_threshold
        assert isinstance(_goodwill_threshold(), float)

    def test_pledge(self):
        from business.screening_service import _pledge_threshold
        assert isinstance(_pledge_threshold(), float)


class TestLimit:
    def test_default(self):
        from business.screening_service import _limit
        assert _limit("test_key", 42) == 42
