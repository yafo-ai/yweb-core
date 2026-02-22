"""ORM 模型测试

测试定时任务相关的 ORM 模型。
"""

import pytest
from datetime import datetime, date

from yweb.scheduler import create_scheduler_models
from yweb.scheduler.models import (
    AbstractSchedulerJob,
    AbstractSchedulerJobHistory,
    AbstractSchedulerJobStats,
)


# 创建测试用的具体模型
_test_models = None


def get_test_models():
    """获取测试用的 scheduler 模型"""
    global _test_models
    if _test_models is None:
        _test_models = create_scheduler_models(table_prefix="test_unit_")
    return _test_models


@pytest.fixture(scope="module")
def scheduler_models():
    """获取 scheduler 模型容器"""
    return get_test_models()


class TestAbstractSchedulerJobModel:
    """AbstractSchedulerJob 抽象模型测试"""
    
    def test_model_is_abstract(self):
        """测试模型是抽象类"""
        assert AbstractSchedulerJob.__abstract__ == True
    
    def test_abstract_model_attributes(self):
        """测试抽象模型属性定义"""
        # 检查模型定义了必要的字段（属性在抽象类中也是存在的）
        assert hasattr(AbstractSchedulerJob, 'code')
        assert hasattr(AbstractSchedulerJob, 'name')
        assert hasattr(AbstractSchedulerJob, 'description')
        assert hasattr(AbstractSchedulerJob, 'trigger_type')
        assert hasattr(AbstractSchedulerJob, 'trigger_args')
        assert hasattr(AbstractSchedulerJob, 'func_ref')
        assert hasattr(AbstractSchedulerJob, 'is_enabled')
        assert hasattr(AbstractSchedulerJob, 'next_run_time')


class TestSchedulerJobModel:
    """SchedulerJob 具体模型测试"""
    
    def test_model_attributes(self, scheduler_models):
        """测试模型属性"""
        SchedulerJob = scheduler_models.SchedulerJob
        
        # 检查模型定义了必要的字段
        assert hasattr(SchedulerJob, 'code')
        assert hasattr(SchedulerJob, 'name')
        assert hasattr(SchedulerJob, 'description')
        assert hasattr(SchedulerJob, 'trigger_type')
        assert hasattr(SchedulerJob, 'trigger_args')
        assert hasattr(SchedulerJob, 'func_ref')
        assert hasattr(SchedulerJob, 'is_enabled')
        assert hasattr(SchedulerJob, 'next_run_time')
    
    def test_model_tablename(self, scheduler_models):
        """测试表名"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert SchedulerJob.__tablename__ == "test_unit_scheduler_job"
    
    def test_model_not_abstract(self, scheduler_models):
        """测试模型不是抽象类"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert not getattr(SchedulerJob, '__abstract__', False)
    
    def test_model_execution_config(self, scheduler_models):
        """测试执行配置字段"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert hasattr(SchedulerJob, 'executor')
        assert hasattr(SchedulerJob, 'concurrent')
        assert hasattr(SchedulerJob, 'max_instances')
        assert hasattr(SchedulerJob, 'timeout')
    
    def test_model_retry_config(self, scheduler_models):
        """测试重试配置字段"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert hasattr(SchedulerJob, 'max_retries')
        assert hasattr(SchedulerJob, 'retry_delay')
        assert hasattr(SchedulerJob, 'retry_backoff')
    
    def test_model_stats_fields(self, scheduler_models):
        """测试统计字段"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert hasattr(SchedulerJob, 'run_count')
        assert hasattr(SchedulerJob, 'success_count')
        assert hasattr(SchedulerJob, 'fail_count')
        assert hasattr(SchedulerJob, 'last_run_time')
        assert hasattr(SchedulerJob, 'last_run_id')
        assert hasattr(SchedulerJob, 'last_status')
    
    def test_model_misfire_config(self, scheduler_models):
        """测试容错配置字段"""
        SchedulerJob = scheduler_models.SchedulerJob
        assert hasattr(SchedulerJob, 'misfire_grace_time')
        assert hasattr(SchedulerJob, 'coalesce')


class TestAbstractSchedulerJobHistoryModel:
    """AbstractSchedulerJobHistory 抽象模型测试"""
    
    def test_model_is_abstract(self):
        """测试模型是抽象类"""
        assert AbstractSchedulerJobHistory.__abstract__ == True


class TestSchedulerJobHistoryModel:
    """SchedulerJobHistory 具体模型测试"""
    
    def test_model_attributes(self, scheduler_models):
        """测试模型属性"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert hasattr(SchedulerJobHistory, 'run_id')
        assert hasattr(SchedulerJobHistory, 'job_id')
        assert hasattr(SchedulerJobHistory, 'job_code')
        assert hasattr(SchedulerJobHistory, 'job_name')
        assert hasattr(SchedulerJobHistory, 'status')
    
    def test_model_tablename(self, scheduler_models):
        """测试表名"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert SchedulerJobHistory.__tablename__ == "test_unit_scheduler_job_history"
    
    def test_model_not_abstract(self, scheduler_models):
        """测试模型不是抽象类"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert not getattr(SchedulerJobHistory, '__abstract__', False)
    
    def test_model_time_fields(self, scheduler_models):
        """测试时间字段"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert hasattr(SchedulerJobHistory, 'scheduled_time')
        assert hasattr(SchedulerJobHistory, 'start_time')
        assert hasattr(SchedulerJobHistory, 'end_time')
        assert hasattr(SchedulerJobHistory, 'duration_ms')
    
    def test_model_result_fields(self, scheduler_models):
        """测试结果字段"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert hasattr(SchedulerJobHistory, 'result')
        assert hasattr(SchedulerJobHistory, 'error')
        assert hasattr(SchedulerJobHistory, 'traceback')
    
    def test_model_retry_fields(self, scheduler_models):
        """测试重试字段"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert hasattr(SchedulerJobHistory, 'attempt')
        assert hasattr(SchedulerJobHistory, 'retry_of')
        assert hasattr(SchedulerJobHistory, 'trigger_type')
    
    def test_model_environment_fields(self, scheduler_models):
        """测试执行环境字段"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        assert hasattr(SchedulerJobHistory, 'hostname')
        assert hasattr(SchedulerJobHistory, 'process_id')


class TestAbstractSchedulerJobStatsModel:
    """AbstractSchedulerJobStats 抽象模型测试"""
    
    def test_model_is_abstract(self):
        """测试模型是抽象类"""
        assert AbstractSchedulerJobStats.__abstract__ == True


class TestSchedulerJobStatsModel:
    """SchedulerJobStats 具体模型测试"""
    
    def test_model_attributes(self, scheduler_models):
        """测试模型属性"""
        SchedulerJobStats = scheduler_models.SchedulerJobStats
        assert hasattr(SchedulerJobStats, 'job_id')
        assert hasattr(SchedulerJobStats, 'job_code')
        assert hasattr(SchedulerJobStats, 'stat_date')
        assert hasattr(SchedulerJobStats, 'stat_hour')
    
    def test_model_tablename(self, scheduler_models):
        """测试表名"""
        SchedulerJobStats = scheduler_models.SchedulerJobStats
        assert SchedulerJobStats.__tablename__ == "test_unit_scheduler_job_stats"
    
    def test_model_not_abstract(self, scheduler_models):
        """测试模型不是抽象类"""
        SchedulerJobStats = scheduler_models.SchedulerJobStats
        assert not getattr(SchedulerJobStats, '__abstract__', False)
    
    def test_model_count_fields(self, scheduler_models):
        """测试计数字段"""
        SchedulerJobStats = scheduler_models.SchedulerJobStats
        assert hasattr(SchedulerJobStats, 'total_runs')
        assert hasattr(SchedulerJobStats, 'success_runs')
        assert hasattr(SchedulerJobStats, 'failed_runs')
        assert hasattr(SchedulerJobStats, 'timeout_runs')
        assert hasattr(SchedulerJobStats, 'retry_runs')
    
    def test_model_duration_fields(self, scheduler_models):
        """测试耗时字段"""
        SchedulerJobStats = scheduler_models.SchedulerJobStats
        assert hasattr(SchedulerJobStats, 'min_duration')
        assert hasattr(SchedulerJobStats, 'max_duration')
        assert hasattr(SchedulerJobStats, 'avg_duration')
        assert hasattr(SchedulerJobStats, 'total_duration')


class TestCreateSchedulerModels:
    """create_scheduler_models 工厂函数测试"""
    
    def test_create_with_default_prefix(self):
        """测试默认前缀创建"""
        models = create_scheduler_models()
        
        assert models.SchedulerJob.__tablename__ == "scheduler_job"
        assert models.SchedulerJobHistory.__tablename__ == "scheduler_job_history"
        assert models.SchedulerJobStats.__tablename__ == "scheduler_job_stats"
    
    def test_create_with_custom_prefix(self):
        """测试自定义前缀创建"""
        models = create_scheduler_models(table_prefix="sys_")
        
        assert models.SchedulerJob.__tablename__ == "sys_scheduler_job"
        assert models.SchedulerJobHistory.__tablename__ == "sys_scheduler_job_history"
        assert models.SchedulerJobStats.__tablename__ == "sys_scheduler_job_stats"
    
    def test_create_with_custom_tablename(self):
        """测试自定义表名"""
        models = create_scheduler_models(
            job_tablename="custom_jobs",
            history_tablename="custom_history",
            stats_tablename="custom_stats",
        )
        
        assert models.SchedulerJob.__tablename__ == "custom_jobs"
        assert models.SchedulerJobHistory.__tablename__ == "custom_history"
        assert models.SchedulerJobStats.__tablename__ == "custom_stats"
    
    def test_models_container_has_all_models(self):
        """测试模型容器包含所有模型"""
        models = create_scheduler_models()
        
        assert hasattr(models, 'SchedulerJob')
        assert hasattr(models, 'SchedulerJobHistory')
        assert hasattr(models, 'SchedulerJobStats')
    
    def test_models_container_as_dict(self):
        """测试模型容器 as_dict 方法"""
        models = create_scheduler_models()
        d = models.as_dict()
        
        assert 'job_model' in d
        assert 'history_model' in d
        assert 'stats_model' in d
