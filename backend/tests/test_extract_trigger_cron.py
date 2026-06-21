"""_extract_trigger_cron / _write_cron_to_dag 的单元测试（纯 DAG 解析，不触及 DB）。"""
import pytest

from app.routers.workflows import _extract_trigger_cron, _write_cron_to_dag


class TestExtractTriggerCron:
    """从 DAG JSON 里提取 trigger 步骤的 cron"""

    def test_schedule_key(self) -> None:
        dag = [
            {"id": "t1", "step_type": "trigger", "config": {"schedule": "0 9 * * *"}},
            {"id": "s1", "step_type": "tool", "tool_name": "noop"},
        ]
        assert _extract_trigger_cron(dag) == "0 9 * * *"

    def test_cron_key_also_supported(self) -> None:
        dag = [{"id": "t1", "step_type": "trigger", "config": {"cron": "*/5 * * * *"}}]
        assert _extract_trigger_cron(dag) == "*/5 * * * *"

    def test_schedule_takes_precedence_over_cron(self) -> None:
        """两个字段都有时，schedule 优先（与原 create_workflow 行为一致）。"""
        dag = [{
            "id": "t1",
            "step_type": "trigger",
            "config": {"schedule": "0 9 * * *", "cron": "*/5 * * * *"},
        }]
        assert _extract_trigger_cron(dag) == "0 9 * * *"

    def test_invalid_cron_ignored(self) -> None:
        """不合法的 cron 不会被采纳（避免把脏数据写进 Schedule 表）。"""
        dag = [{"id": "t1", "step_type": "trigger", "config": {"schedule": "not cron"}}]
        assert _extract_trigger_cron(dag) is None

    def test_no_trigger_step(self) -> None:
        dag = [{"id": "s1", "step_type": "tool", "tool_name": "noop"}]
        assert _extract_trigger_cron(dag) is None

    def test_trigger_without_config(self) -> None:
        dag = [{"id": "t1", "step_type": "trigger"}]
        assert _extract_trigger_cron(dag) is None

    def test_trigger_with_none_config(self) -> None:
        dag = [{"id": "t1", "step_type": "trigger", "config": None}]
        assert _extract_trigger_cron(dag) is None

    def test_empty_list(self) -> None:
        assert _extract_trigger_cron([]) is None

    def test_non_list_input(self) -> None:
        assert _extract_trigger_cron(None) is None
        assert _extract_trigger_cron({"not": "a list"}) is None

    def test_dict_with_steps_key(self) -> None:
        """真实 dag_json 是 dict（含 steps 键），不应被拒绝。

        回归测试：旧版函数只接受 list，导致 update_workflow 收到 dict 时
        永远拿不到 cron，触发误禁用已有 Schedule 的 bug。
        """
        dag = {
            "name": "demo",
            "description": "",
            "steps": [
                {"id": "t1", "step_type": "trigger", "config": {"schedule": "0 9 * * *"}},
                {"id": "s1", "step_type": "tool", "tool_name": "noop"},
            ],
        }
        assert _extract_trigger_cron(dag) == "0 9 * * *"

    def test_dict_without_steps_key(self) -> None:
        """dict 但没有 steps 键 → 安全返回 None，不抛异常。"""
        assert _extract_trigger_cron({"name": "x", "description": "y"}) is None

    def test_dict_with_non_list_steps(self) -> None:
        """steps 存在但不是 list（脏数据）→ 返回 None。"""
        assert _extract_trigger_cron({"steps": "not a list"}) is None

    def test_first_valid_cron_wins(self) -> None:
        """多个 trigger 步骤时，取第一个合法 cron（与 create_workflow 行为一致）。"""
        dag = [
            {"id": "t1", "step_type": "trigger", "config": {"schedule": "0 9 * * *"}},
            {"id": "t2", "step_type": "trigger", "config": {"schedule": "0 10 * * *"}},
        ]
        assert _extract_trigger_cron(dag) == "0 9 * * *"

    def test_skips_non_dict_step(self) -> None:
        """DAG 里混入非字典元素（脏数据）不应让函数抛异常。"""
        dag = ["garbage", {"id": "t1", "step_type": "trigger", "config": {"schedule": "0 9 * * *"}}]
        assert _extract_trigger_cron(dag) == "0 9 * * *"


class TestWriteCronToDag:
    """把 cron 写回 dag_json 的 trigger.config.schedule"""

    def test_write_into_dict_dag(self) -> None:
        dag = {
            "name": "x",
            "steps": [{"id": "t1", "step_type": "trigger", "config": {}}],
        }
        _write_cron_to_dag(dag, "0 9 * * *")
        assert dag["steps"][0]["config"]["schedule"] == "0 9 * * *"

    def test_replaces_legacy_cron_key(self) -> None:
        """写入新 schedule 时清掉旧别名 cron，避免两个字段并存歧义。"""
        dag = {"steps": [{"id": "t1", "step_type": "trigger", "config": {"cron": "*/5 * * * *"}}]}
        _write_cron_to_dag(dag, "0 9 * * *")
        assert dag["steps"][0]["config"]["schedule"] == "0 9 * * *"
        assert "cron" not in dag["steps"][0]["config"]

    def test_creates_config_when_missing(self) -> None:
        dag = {"steps": [{"id": "t1", "step_type": "trigger"}]}
        _write_cron_to_dag(dag, "0 9 * * *")
        assert dag["steps"][0]["config"]["schedule"] == "0 9 * * *"

    def test_only_first_trigger_updated(self) -> None:
        dag = {
            "steps": [
                {"id": "t1", "step_type": "trigger", "config": {}},
                {"id": "t2", "step_type": "trigger", "config": {}},
            ]
        }
        _write_cron_to_dag(dag, "0 9 * * *")
        assert dag["steps"][0]["config"]["schedule"] == "0 9 * * *"
        assert "schedule" not in dag["steps"][1]["config"]

    def test_no_trigger_is_noop(self) -> None:
        """没有 trigger 步骤时不应抛异常（保持 dag_json 原样）。"""
        dag = {"steps": [{"id": "s1", "step_type": "tool", "tool_name": "noop"}]}
        before = dict(dag)
        _write_cron_to_dag(dag, "0 9 * * *")
        assert dag == before

    def test_non_dict_non_list_is_passthrough(self) -> None:
        assert _write_cron_to_dag(None, "0 9 * * *") is None
        assert _write_cron_to_dag("string", "0 9 * * *") == "string"
