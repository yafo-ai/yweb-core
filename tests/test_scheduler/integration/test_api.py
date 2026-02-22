"""管理 API 测试

测试调度器管理 API 功能。使用动词风格路由。
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.scheduler import Scheduler, cron, interval
from yweb.scheduler.api import create_scheduler_router, setup_scheduler_api


@pytest.fixture
def scheduler():
    """创建测试用调度器"""
    s = Scheduler()
    
    @s.cron("0 8 * * *", code="TEST_JOB", name="测试任务")
    async def test_job():
        pass
    
    @s.interval(minutes=30, code="INTERVAL_JOB", name="间隔任务")
    async def interval_job():
        pass
    
    return s


@pytest.fixture
def app(scheduler):
    """创建测试用 FastAPI 应用"""
    test_app = FastAPI()
    router = create_scheduler_router(scheduler)
    test_app.include_router(router, prefix="/api/scheduler")
    return test_app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


class TestGetJobs:
    """获取任务列表测试"""
    
    def test_get_jobs(self, client):
        """测试获取所有任务"""
        response = client.get("/api/scheduler/jobs/list")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)
        
        codes = [j["code"] for j in data["data"]]
        assert "TEST_JOB" in codes
        assert "INTERVAL_JOB" in codes
    
    def test_get_job_detail(self, client):
        """测试获取任务详情"""
        response = client.get("/api/scheduler/jobs/get?code=TEST_JOB")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["code"] == "TEST_JOB"
        assert data["data"]["name"] == "测试任务"
    
    def test_get_nonexistent_job(self, client):
        """测试获取不存在的任务"""
        response = client.get("/api/scheduler/jobs/get?code=NOT_EXIST")
        
        # NotFound 返回 HTTP 404
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"

    def test_get_jobs_excludes_child_jobs(self, client, scheduler):
        """测试任务列表会过滤 parent_code 子任务"""
        child_job = scheduler._jobs["TEST_JOB"].copy()
        child_job["code"] = "TEST_JOB#2"
        child_job["parent_code"] = "TEST_JOB"
        scheduler._jobs["TEST_JOB#2"] = child_job

        response = client.get("/api/scheduler/jobs/list")
        assert response.status_code == 200
        data = response.json()
        codes = [j["code"] for j in data["data"]]
        assert "TEST_JOB" in codes
        assert "TEST_JOB#2" not in codes


class TestJobControl:
    """任务控制测试"""
    
    def test_run_job_returns_run_id(self, client, scheduler):
        """测试立即执行任务返回稳定且可验证的响应"""
        with patch.object(scheduler, "run_job", return_value="run_test_123") as mock_run:
            response = client.post("/api/scheduler/jobs/run?code=TEST_JOB")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "任务已触发"
        assert data["data"]["run_id"] == "run_test_123"
        assert data["data"]["job_code"] == "TEST_JOB"
        mock_run.assert_called_once_with("TEST_JOB")
    
    def test_run_nonexistent_job(self, client):
        """测试执行不存在的任务"""
        response = client.post("/api/scheduler/jobs/run?code=NOT_EXIST")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
    
    def test_pause_job(self, client, scheduler):
        """测试暂停任务"""
        response = client.post("/api/scheduler/jobs/pause?code=TEST_JOB")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # 验证任务已暂停
        assert scheduler._jobs["TEST_JOB"]["is_paused"] == True
    
    def test_resume_job(self, client, scheduler):
        """测试恢复任务"""
        # 先暂停
        scheduler.pause_job("TEST_JOB")
        
        # 再恢复
        response = client.post("/api/scheduler/jobs/resume?code=TEST_JOB")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # 验证任务已恢复
        assert scheduler._jobs["TEST_JOB"]["is_paused"] == False
    
    def test_delete_job(self, client, scheduler):
        """测试删除任务"""
        response = client.post("/api/scheduler/jobs/delete?code=INTERVAL_JOB")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # 验证任务已删除
        assert "INTERVAL_JOB" not in scheduler._jobs

    def test_pause_nonexistent_job_returns_not_found(self, client, scheduler):
        """测试暂停不存在的任务返回 404"""
        with patch.object(scheduler, "pause_job", return_value=False) as mock_pause:
            response = client.post("/api/scheduler/jobs/pause?code=NOT_EXIST")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "不存在或暂停失败" in data["message"]
        mock_pause.assert_called_once_with("NOT_EXIST")

    def test_resume_nonexistent_job_returns_not_found(self, client, scheduler):
        """测试恢复不存在的任务返回 404"""
        with patch.object(scheduler, "resume_job", return_value=False) as mock_resume:
            response = client.post("/api/scheduler/jobs/resume?code=NOT_EXIST")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "不存在或恢复失败" in data["message"]
        mock_resume.assert_called_once_with("NOT_EXIST")

    def test_delete_nonexistent_job_returns_not_found(self, client, scheduler):
        """测试删除不存在的任务返回 404"""
        with patch.object(scheduler, "remove_job", return_value=False) as mock_remove:
            response = client.post("/api/scheduler/jobs/delete?code=NOT_EXIST")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "不存在" in data["message"]
        mock_remove.assert_called_once_with("NOT_EXIST")


class TestGetStats:
    """获取统计测试"""
    
    def test_get_stats(self, client):
        """测试获取统计信息"""
        response = client.get("/api/scheduler/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "total_jobs" in data["data"]
        assert "is_running" in data["data"]
    
    def test_get_status(self, client):
        """测试获取调度器状态"""
        response = client.get("/api/scheduler/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "is_running" in data["data"]
        assert "enabled" in data["data"]


class TestExecutions:
    """执行历史测试"""
    
    def test_get_executions_endpoint_structure(self, client):
        """测试执行历史端点存在且返回正确结构"""
        response = client.get("/api/scheduler/executions/list")
        
        # 无数据库时返回空分页
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # 验证分页结构
        assert isinstance(data["data"], dict)
        assert "rows" in data["data"]
        assert "total_records" in data["data"]
        assert "page" in data["data"]
        assert "page_size" in data["data"]
        assert isinstance(data["data"]["rows"], list)

    def test_get_execution_not_found_when_history_disabled(self, client):
        """测试历史未启用时获取执行详情返回 404"""
        with patch("tests.test_scheduler.integration.test_api.Scheduler._get_history_manager", return_value=None):
            response = client.get("/api/scheduler/executions/get?run_id=missing_run")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "历史记录未启用" in data["message"]


class TestExecutionsWithDatabase:
    """使用内存数据库的执行历史测试"""
    
    @pytest.fixture
    def db_scheduler(self, scheduler_db_session, scheduler_models):
        """创建带数据库的测试调度器"""
        s = Scheduler()
        
        @s.cron("0 8 * * *", code="DB_TEST_JOB", name="数据库测试任务")
        async def db_test_job():
            pass
        
        # 注入模型到 history manager
        if s._history_manager is None:
            s._get_history_manager()
        if s._history_manager:
            s._history_manager._job_model = scheduler_models.SchedulerJob
            s._history_manager._history_model = scheduler_models.SchedulerJobHistory
            s._history_manager._stats_model = scheduler_models.SchedulerJobStats
        
        return s
    
    @pytest.fixture
    def db_app(self, db_scheduler, scheduler_models):
        """创建带数据库的测试应用"""
        test_app = FastAPI()
        router = create_scheduler_router(
            db_scheduler,
            history_model=scheduler_models.SchedulerJobHistory,
        )
        test_app.include_router(router, prefix="/api/scheduler")
        return test_app
    
    @pytest.fixture
    def db_client(self, db_app):
        """创建数据库测试客户端"""
        return TestClient(db_app)
    
    def test_get_executions_with_database(self, db_client, scheduler_db_session, scheduler_models):
        """测试有数据库时的执行历史查询"""
        from datetime import datetime
        
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        
        # 插入测试数据
        history = SchedulerJobHistory(
            job_id="test_job_id",
            job_code="DB_TEST_JOB",
            job_name="数据库测试任务",
            run_id="test_run_001",
            status="success",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=100,
        )
        history.save(commit=True)
        
        # 查询
        response = db_client.get("/api/scheduler/executions/list?job_code=DB_TEST_JOB")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # 验证分页结构
        assert "rows" in data["data"]
        assert len(data["data"]["rows"]) >= 1
        assert data["data"]["rows"][0]["job_code"] == "DB_TEST_JOB"
    
    def test_get_execution_detail(self, db_client, scheduler_db_session, scheduler_models):
        """测试获取执行详情"""
        from datetime import datetime
        
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        
        # 插入测试数据
        history = SchedulerJobHistory(
            job_id="detail_job_id",
            job_code="DETAIL_JOB",
            job_name="详情任务",
            run_id="detail_run_001",
            status="success",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=150,
        )
        history.save(commit=True)
        
        # 查询详情
        response = db_client.get("/api/scheduler/executions/get?run_id=detail_run_001")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["run_id"] == "detail_run_001"
    
    def test_get_dashboard_with_database(self, db_client, scheduler_db_session):
        """测试仪表板数据"""
        response = db_client.get("/api/scheduler/dashboard")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "today" in data["data"]
        assert "yesterday" in data["data"]
        assert "this_week" in data["data"]
    
    def test_cleanup_history(self, db_client, scheduler_db_session):
        """测试清理历史记录"""
        response = db_client.post("/api/scheduler/cleanup?days=30")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "history" in data["data"]
        assert "stats" in data["data"]


class _BrokenHistoryQuery:
    """用于触发 execution_api 异常分支的查询对象"""

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        raise RuntimeError("broken query")


class _BrokenHistoryField:
    """模拟 ORM 字段，支持比较运算但不执行任何数据库操作"""

    def __eq__(self, _other):
        return object()

    def __ge__(self, _other):
        return object()

    def __le__(self, _other):
        return object()

    def desc(self):
        return object()


class _BrokenHistoryModel:
    """最小化历史模型替身，用于覆盖异常分支"""

    query = _BrokenHistoryQuery()
    job_code = _BrokenHistoryField()
    status = _BrokenHistoryField()
    start_time = _BrokenHistoryField()


class TestApiEdgeBranches:
    """API 边界分支测试"""

    def test_executions_list_returns_empty_when_history_manager_none(self):
        """测试 history_model 存在但 history manager 为空时返回空分页"""
        scheduler = Scheduler()
        with patch.object(scheduler, "_get_history_manager", return_value=None):
            app = FastAPI()
            app.include_router(
                create_scheduler_router(scheduler, history_model=_BrokenHistoryModel),
                prefix="/api/scheduler",
            )
            client = TestClient(app)
            response = client.get("/api/scheduler/executions/list?job_code=A&status=success")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["rows"] == []
        assert data["data"]["total_records"] == 0

    def test_executions_list_returns_empty_when_query_raises(self):
        """测试历史查询异常时降级为空分页"""
        scheduler = Scheduler()
        app = FastAPI()
        app.include_router(
            create_scheduler_router(scheduler, history_model=_BrokenHistoryModel),
            prefix="/api/scheduler",
        )
        client = TestClient(app)
        response = client.get(
            "/api/scheduler/executions/list"
            "?job_code=X&status=failed&start_date=2026-01-01&end_date=2026-01-02"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["rows"] == []
        assert data["data"]["total_records"] == 0

    def test_execution_get_returns_not_found_when_scheduler_has_no_record(self):
        """测试 history 已启用但记录不存在时返回 404"""
        scheduler = Scheduler()
        fake_history_manager = Mock()
        with patch.object(scheduler, "_get_history_manager", return_value=fake_history_manager), \
             patch.object(scheduler, "get_execution", return_value=None):
            app = FastAPI()
            app.include_router(create_scheduler_router(scheduler), prefix="/api/scheduler")
            client = TestClient(app)
            response = client.get("/api/scheduler/executions/get?run_id=unknown_run")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "不存在" in data["message"]

    def test_execution_get_returns_not_found_when_history_manager_attr_error(self):
        """测试获取执行详情时 history manager 属性错误返回 404"""
        scheduler = Scheduler()
        with patch.object(scheduler, "_get_history_manager", side_effect=AttributeError):
            app = FastAPI()
            app.include_router(create_scheduler_router(scheduler), prefix="/api/scheduler")
            client = TestClient(app)
            response = client.get("/api/scheduler/executions/get?run_id=unknown_run")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert "历史记录未启用" in data["message"]

    def test_dashboard_returns_default_when_history_manager_attr_error(self):
        """测试 dashboard 在 AttributeError 时返回默认结构"""
        scheduler = Scheduler()
        with patch.object(scheduler, "_get_history_manager", side_effect=AttributeError):
            app = FastAPI()
            app.include_router(create_scheduler_router(scheduler), prefix="/api/scheduler")
            client = TestClient(app)
            response = client.get("/api/scheduler/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["today"] == {}
        assert data["data"]["recent_failures"] == []

    def test_cleanup_returns_noop_when_history_manager_none(self):
        """测试 cleanup 在历史未启用时返回无操作结果"""
        scheduler = Scheduler()
        with patch.object(scheduler, "_get_history_manager", return_value=None):
            app = FastAPI()
            app.include_router(create_scheduler_router(scheduler), prefix="/api/scheduler")
            client = TestClient(app)
            response = client.post("/api/scheduler/cleanup?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"] == {"history": 0, "stats": 0}
        assert "无需清理" in data["message"]

    def test_cleanup_returns_noop_when_history_manager_attr_error(self):
        """测试 cleanup 在 history manager 属性异常时返回无操作结果"""
        scheduler = Scheduler()
        with patch.object(scheduler, "_get_history_manager", side_effect=AttributeError):
            app = FastAPI()
            app.include_router(create_scheduler_router(scheduler), prefix="/api/scheduler")
            client = TestClient(app)
            response = client.post("/api/scheduler/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"] == {"history": 0, "stats": 0}
        assert "无需清理" in data["message"]


class TestSetupSchedulerApi:
    """快速设置 API 测试"""
    
    def test_setup_function(self):
        """测试 setup_scheduler_api 函数"""
        app = FastAPI()
        scheduler = Scheduler()
        
        setup_scheduler_api(app, scheduler)
        
        # 检查路由已添加
        routes = [r.path for r in app.routes]
        assert any("/api/scheduler" in r for r in routes)
    
    def test_setup_with_custom_prefix(self):
        """测试自定义前缀"""
        app = FastAPI()
        scheduler = Scheduler()
        
        setup_scheduler_api(app, scheduler, prefix="/scheduler")
        
        routes = [r.path for r in app.routes]
        assert any("/scheduler" in r for r in routes)


class TestCreateSchedulerRouter:
    """创建路由测试"""
    
    def test_router_has_jobs_routes(self):
        """测试路由包含任务管理端点"""
        scheduler = Scheduler()
        router = create_scheduler_router(scheduler)
        
        paths = [r.path for r in router.routes]
        
        assert "/jobs/list" in paths
        assert "/jobs/get" in paths
        assert "/stats" in paths
        assert "/status" in paths
    
    def test_router_methods(self):
        """测试路由方法正确"""
        scheduler = Scheduler()
        router = create_scheduler_router(scheduler)
        
        # 找到 jobs/run 路由
        run_route = None
        for r in router.routes:
            if hasattr(r, 'path') and r.path == "/jobs/run":
                run_route = r
                break
        
        assert run_route is not None
        assert "POST" in run_route.methods
