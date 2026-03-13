"""Tests for runner module — RunSummary and TaskResult."""

from appworld_a2a_runner.runner import RunSummary, TaskResult


class TestTaskResult:
    """Tests for TaskResult data container."""

    def test_success_result(self):
        r = TaskResult(task_id="t1", success=True, latency_ms=150.0, response_chars=42)
        assert r.task_id == "t1"
        assert r.success is True
        assert r.latency_ms == 150.0
        assert r.error is None
        assert r.response_chars == 42

    def test_failure_result(self):
        r = TaskResult(task_id="t2", success=False, latency_ms=50.0, error="Timeout")
        assert r.success is False
        assert r.error == "Timeout"


class TestRunSummary:
    """Tests for RunSummary statistics."""

    def test_empty_summary(self):
        s = RunSummary(dataset="test")
        summary = s.get_summary()
        assert summary["dataset"] == "test"
        assert summary["tasks_attempted"] == 0
        assert summary["tasks_succeeded"] == 0
        assert summary["tasks_failed"] == 0
        assert summary["average_latency_ms"] == 0

    def test_single_success(self):
        s = RunSummary(dataset="test")
        s.add_result(TaskResult("t1", success=True, latency_ms=100.0))
        summary = s.get_summary()
        assert summary["tasks_attempted"] == 1
        assert summary["tasks_succeeded"] == 1
        assert summary["tasks_failed"] == 0
        assert summary["average_latency_ms"] == 100.0

    def test_mixed_results(self):
        s = RunSummary(dataset="test")
        s.add_result(TaskResult("t1", success=True, latency_ms=100.0))
        s.add_result(TaskResult("t2", success=False, latency_ms=200.0, error="fail"))
        s.add_result(TaskResult("t3", success=True, latency_ms=300.0))
        summary = s.get_summary()
        assert summary["tasks_attempted"] == 3
        assert summary["tasks_succeeded"] == 2
        assert summary["tasks_failed"] == 1
        assert summary["average_latency_ms"] == 200.0

    def test_percentiles(self):
        s = RunSummary(dataset="test")
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            s.add_result(TaskResult(f"t{ms}", success=True, latency_ms=float(ms)))
        summary = s.get_summary()
        assert summary["p50_latency_ms"] == 60.0
        assert summary["p95_latency_ms"] == 100.0

    def test_wall_time_positive(self):
        s = RunSummary(dataset="test")
        s.add_result(TaskResult("t1", success=True, latency_ms=1.0))
        summary = s.get_summary()
        assert summary["total_wall_time_seconds"] > 0
