"""AsyncExecutor 单元测试"""

import asyncio

import pytest

from yweb.scheduler.executors.async_executor import AsyncExecutor


class TestAsyncExecutor:
    """异步执行器边界与异常路径测试"""

    @pytest.mark.asyncio
    async def test_execute_async_function_success(self):
        """测试执行协程函数成功并清理运行计数"""
        executor = AsyncExecutor(max_instances=2)

        async def async_job(x, y):
            await asyncio.sleep(0)
            return x + y

        result = await executor.execute(async_job, 1, 2, job_id="job_async")

        assert result == 3
        assert executor.get_running_count("job_async") == 0

    @pytest.mark.asyncio
    async def test_execute_sync_function_success(self):
        """测试执行同步函数成功"""
        executor = AsyncExecutor(max_instances=1)

        def sync_job(x, y):
            return x * y

        result = await executor.execute(sync_job, 3, 4, job_id="job_sync")

        assert result == 12
        assert executor.get_running_count("job_sync") == 0

    @pytest.mark.asyncio
    async def test_max_instances_reached_returns_none(self):
        """测试达到并发上限时返回 None 且不增加计数"""
        executor = AsyncExecutor(max_instances=1)
        gate = asyncio.Event()

        async def blocking_job():
            await gate.wait()
            return "done"

        task = asyncio.create_task(executor.execute(blocking_job, job_id="same_job"))
        await asyncio.sleep(0.05)

        rejected = await executor.execute(blocking_job, job_id="same_job")
        assert rejected is None
        assert executor.get_running_count("same_job") == 1

        gate.set()
        assert await task == "done"
        assert executor.get_running_count("same_job") == 0

    @pytest.mark.asyncio
    async def test_execute_raises_and_cleans_running_count(self):
        """测试任务异常会向上抛出并清理运行计数"""
        executor = AsyncExecutor(max_instances=1)

        async def failed_job():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await executor.execute(failed_job, job_id="job_error")

        assert executor.get_running_count("job_error") == 0

    @pytest.mark.asyncio
    async def test_execute_without_job_id_does_not_track_running_jobs(self):
        """测试不传 job_id 时不记录并发计数"""
        executor = AsyncExecutor(max_instances=1)

        async def async_job():
            return "ok"

        result = await executor.execute(async_job)
        assert result == "ok"
        assert executor._running_jobs == {}

    @pytest.mark.asyncio
    async def test_execute_sync_function_with_kwargs_raises_type_error(self):
        """测试同步函数 + kwargs 时会抛出 TypeError（当前实现限制）"""
        executor = AsyncExecutor(max_instances=1)

        def sync_with_kwargs(*, x):
            return x

        with pytest.raises(TypeError):
            await executor.execute(sync_with_kwargs, job_id="job_kwargs", x=1)

        assert executor.get_running_count("job_kwargs") == 0

    def test_get_running_count_default_zero(self):
        """测试未执行任务时运行计数为 0"""
        executor = AsyncExecutor()
        assert executor.get_running_count("not_exist") == 0
