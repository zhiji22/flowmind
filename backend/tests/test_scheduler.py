"""scheduler.py 的单元测试（纯函数，不触及 DB/Redis）。"""
import pytest
from datetime import datetime, timezone, timedelta

from app.services.scheduler import is_valid_cron, compute_next_run


class TestIsValidCron:
    """cron 表达式合法性校验"""

    @pytest.mark.parametrize(
        "expr",
        [
            "0 9 * * *",        # 每天 9 点
            "*/5 * * * *",      # 每 5 分钟
            "0 0 1 * *",        # 每月 1 号
            "0 0 * * 0",        # 每周日
            "30 2 * * 1-5",     # 工作日凌晨 2:30
        ],
    )
    def test_valid(self, expr: str) -> None:
        assert is_valid_cron(expr) is True

    @pytest.mark.parametrize(
        "expr",
        [
            "",
            "not a cron",
            "0 9",              # 段数不足
            "0 9 * * * *",      # 段数过多（6 段，本项目要求 5 段）
            "99 99 * * *",      # 字段越界
            "* * * *",          # 4 段
        ],
    )
    def test_invalid(self, expr: str) -> None:
        assert is_valid_cron(expr) is False

    def test_non_string_rejected(self) -> None:
        assert is_valid_cron(None) is False  # type: ignore[arg-type]
        assert is_valid_cron(123) is False    # type: ignore[arg-type]


class TestComputeNextRun:
    """根据 cron 计算下次运行时间（UTC tz-aware）"""

    def test_returns_tz_aware(self) -> None:
        result = compute_next_run("0 9 * * *")
        assert result.tzinfo is not None

    def test_specific_base(self) -> None:
        """给定的基准时间 9:00:00，下次 9 点应为次日 9:00。"""
        base = datetime(2026, 6, 20, 9, 0, 0, tzinfo=timezone.utc)
        nxt = compute_next_run("0 9 * * *", base=base)
        assert nxt == datetime(2026, 6, 21, 9, 0, 0, tzinfo=timezone.utc)

    def test_next_beats_now(self) -> None:
        """返回的下次时间必须严格大于基准时间。"""
        base = datetime(2026, 6, 20, 8, 59, 59, tzinfo=timezone.utc)
        nxt = compute_next_run("0 9 * * *", base=base)
        assert nxt > base
        assert nxt.minute == 0
        assert nxt.hour == 9

    def test_every_minute_advances(self) -> None:
        base = datetime(2026, 6, 20, 9, 0, 0, tzinfo=timezone.utc)
        nxt = compute_next_run("* * * * *", base=base)
        assert nxt == base + timedelta(minutes=1)
