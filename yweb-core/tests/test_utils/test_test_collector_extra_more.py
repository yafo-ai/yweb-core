"""test_collector 模块补充测试。"""

import pytest

import yweb.utils.test_collector as tc_mod


class DemoError(Exception):
    pass


class TestCollectorExtraMore:
    """TestCollector 低覆盖分支补测。"""

    def test_run_test_pass_fail_and_error(self, capsys):
        collector = tc_mod.TestCollector(title="Demo", verbose=True)

        assert collector.run_test("ok", lambda: None) is True
        assert collector.run_test("fail", lambda: (_ for _ in ()).throw(AssertionError("bad"))) is False
        assert collector.run_test("err", lambda: (_ for _ in ()).throw(DemoError("boom"))) is False

        out = capsys.readouterr().out
        assert "ok" in out
        assert "fail" in out
        assert "DemoError" in out

    def test_check_helpers_and_properties(self):
        collector = tc_mod.TestCollector(verbose=False)
        collector.check("c1", True)
        collector.check("c2", False, "broken")
        collector.check_equal("eq1", 1, 1)
        collector.check_equal("eq2", 1, 2)
        collector.check_not_none("nn", 1)
        collector.check_not_none("nn2", None)
        collector.check_true("t1", "x")
        collector.check_true("t2", "")

        assert collector.total == 8
        assert collector.passed_count == 4
        assert collector.failed_count == 4
        assert collector.all_passed is False
        assert len(collector.failed_results) == 4
        assert collector.failed_results[0].passed is False

    def test_section_summary_reset_and_factory(self, capsys):
        collector = tc_mod.create_test_collector(title="模块A", verbose=False)
        collector.section("分节")
        collector.check("p", True)
        collector.check("f", False, "x")
        result = collector.summary()
        out = capsys.readouterr().out

        assert result is False
        assert "模块A - 测试汇总" in out
        assert "[FAIL] f" in out

        collector.reset()
        assert collector.total == 0
        assert collector.results == []

    def test_status_enum_values(self):
        assert tc_mod.TestStatus.PASSED.value == "passed"
        assert tc_mod.TestStatus.FAILED.value == "failed"
        assert tc_mod.TestStatus.ERROR.value == "error"
