"""同步服务安全机制测试

仅测试 BaseSyncService 新增的安全同步功能：
- 安全阈值检查 (_check_safety_threshold)
- 预拉取缓存机制（避免重复 API 调用）
- 部门软删除（deleted_at 替代硬删除）
- 员工标记离职（RESIGNED 替代硬删除）
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from typing import List, Dict, Any, Optional

from yweb.organization.services.sync_service import BaseSyncService, SyncResult
from yweb.organization.enums import ExternalSource, EmployeeStatus


# ==================== 测试用具体实现 ====================


class MockSyncService(BaseSyncService):
    """测试用同步服务

    跟踪 fetch 调用次数，用于验证缓存机制。
    """

    external_source = ExternalSource.WECHAT_WORK

    def __init__(self, departments=None, employees=None):
        self._mock_departments = departments or []
        self._mock_employees = employees or []
        self.fetch_departments_call_count = 0
        self.fetch_employees_call_count = 0

        # 使用 Mock 模型（不初始化父类的 _validate_config）
        self.org_model = MagicMock()
        self.dept_model = MagicMock()
        self.employee_model = MagicMock()
        self.emp_org_rel_model = MagicMock()
        self.emp_dept_rel_model = MagicMock()

        # 手动初始化缓存属性（跳过 _validate_config）
        self._cached_departments = None
        self._cached_employees = None

    def fetch_departments(self, org) -> List[Dict[str, Any]]:
        if self._cached_departments is not None:
            return self._cached_departments
        self.fetch_departments_call_count += 1
        return self._mock_departments

    def fetch_employees(self, org) -> List[Dict[str, Any]]:
        if self._cached_employees is not None:
            return self._cached_employees
        self.fetch_employees_call_count += 1
        return self._mock_employees

    def fetch_organization_info(self, org) -> Optional[Dict[str, Any]]:
        return None


# ==================== 安全阈值测试 ====================


class TestSafetyThreshold:
    """测试安全阈值检查逻辑"""

    def _make_service(self):
        return MockSyncService()

    def test_first_sync_skip_check(self):
        """首次同步（本地为0），跳过检查"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(0, 0, "部门", result)
        assert result.success is True
        assert len(result.errors) == 0

    def test_first_sync_with_external_data(self):
        """首次同步（本地为0，外部有数据），跳过检查"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(0, 50, "部门", result)
        assert result.success is True

    def test_external_empty_with_large_local(self):
        """外部数据为空，本地有大量数据 → 中止"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(100, 0, "部门", result)
        assert result.success is False
        assert "API 故障" in result.errors[0]

    def test_external_empty_with_small_local(self):
        """外部数据为空，本地数据量小（<=10）→ 放行"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(5, 0, "部门", result)
        assert result.success is True

    def test_external_much_less_than_local(self):
        """外部数据远少于本地（<30%）→ 中止"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(100, 20, "员工", result)
        assert result.success is False
        assert "数据异常" in result.errors[0]

    def test_external_slightly_less_than_local(self):
        """外部数据略少于本地（>=30%）→ 放行"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(100, 50, "员工", result)
        assert result.success is True

    def test_small_local_skip_ratio_check(self):
        """本地数据量小（<=20），不做比例检查"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(15, 3, "部门", result)
        assert result.success is True

    def test_normal_sync_passes(self):
        """正常同步（外部数量合理）→ 放行"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(100, 95, "部门", result)
        assert result.success is True

    def test_multiple_checks_accumulate_errors(self):
        """多次检查的错误会累积"""
        svc = self._make_service()
        result = SyncResult()
        svc._check_safety_threshold(100, 0, "部门", result)
        svc._check_safety_threshold(200, 0, "员工", result)
        assert len(result.errors) == 2


# ==================== 缓存机制测试 ====================


class TestFetchCaching:
    """测试预拉取缓存机制"""

    def test_cache_prevents_duplicate_fetch(self):
        """缓存填充后，fetch 不再调用 API"""
        svc = MockSyncService(
            departments=[{"external_dept_id": "1", "name": "A"}],
            employees=[{"external_user_id": "u1", "name": "张三"}],
        )

        # 模拟预拉取（sync_from_external 中的行为）
        org = MagicMock()
        svc._cached_departments = svc.fetch_departments(org)
        svc._cached_employees = svc.fetch_employees(org)
        assert svc.fetch_departments_call_count == 1
        assert svc.fetch_employees_call_count == 1

        # 再次调用应命中缓存
        svc.fetch_departments(org)
        svc.fetch_departments(org)
        svc.fetch_employees(org)
        assert svc.fetch_departments_call_count == 1  # 仍然只调了 1 次
        assert svc.fetch_employees_call_count == 1

    def test_cache_cleared_returns_fresh_data(self):
        """缓存清理后，重新调用 API"""
        svc = MockSyncService(
            departments=[{"external_dept_id": "1", "name": "A"}],
        )
        org = MagicMock()

        svc._cached_departments = svc.fetch_departments(org)
        assert svc.fetch_departments_call_count == 1

        # 清理缓存
        svc._cached_departments = None

        # 应该重新调用 API
        svc.fetch_departments(org)
        assert svc.fetch_departments_call_count == 2

    def test_cache_is_none_by_default(self):
        """初始化时缓存为 None"""
        svc = MockSyncService()
        assert svc._cached_departments is None
        assert svc._cached_employees is None


# ==================== 部门软删除测试 ====================


class TestDepartmentSoftDelete:
    """测试 sync_departments 对本地多出部门的软删除行为"""

    def test_soft_delete_sets_deleted_at(self):
        """本地有、外部没有的部门应设置 deleted_at 而非硬删除"""
        svc = MockSyncService()

        # 模拟外部数据（只有部门 A）
        svc._cached_departments = [
            {"external_dept_id": "1", "name": "A", "external_parent_id": None},
        ]

        # 模拟本地数据（有部门 A 和部门 B）
        mock_dept_a = MagicMock()
        mock_dept_a.external_dept_id = "1"
        mock_dept_a.parent_id = None
        mock_dept_a.org_id = 1

        mock_dept_b = MagicMock()
        mock_dept_b.external_dept_id = "2"
        mock_dept_b.deleted_at = None  # 未被删除

        svc.dept_model.query.filter.return_value.all.return_value = [mock_dept_a, mock_dept_b]

        org = MagicMock()
        org.id = 1

        result = svc.sync_departments(org)

        # 部门 B 应被软删除（设置 deleted_at）
        assert mock_dept_b.deleted_at is not None
        assert isinstance(mock_dept_b.deleted_at, datetime)
        mock_dept_b.save.assert_called()

        # 不应调用 delete()
        mock_dept_b.delete.assert_not_called()

        assert result.deleted_count == 1


# ==================== 员工标记离职测试 ====================


class TestEmployeeMarkResigned:
    """测试 sync_employees 对本地多出员工的离职标记行为"""

    def test_mark_resigned_instead_of_delete(self):
        """本地有、外部没有的员工应标记为离职而非删除"""
        svc = MockSyncService()

        # 模拟外部数据（只有用户 u1）
        svc._cached_employees = [
            {"external_user_id": "u1", "name": "张三"},
        ]

        # 模拟本地数据（有 u1 和 u2）
        mock_rel_u1 = MagicMock()
        mock_rel_u1.external_user_id = "u1"
        mock_rel_u1.employee_id = 1
        mock_rel_u1.status = EmployeeStatus.ACTIVE.value

        mock_rel_u2 = MagicMock()
        mock_rel_u2.external_user_id = "u2"
        mock_rel_u2.employee_id = 2
        mock_rel_u2.status = EmployeeStatus.ACTIVE.value

        svc.emp_org_rel_model.query.filter.return_value.all.return_value = [mock_rel_u1, mock_rel_u2]

        # u1 的 employee mock
        mock_emp = MagicMock()
        svc.employee_model.get.return_value = mock_emp

        org = MagicMock()
        org.id = 1

        result = svc.sync_employees(org)

        # u2 应被标记为离职
        assert mock_rel_u2.status == EmployeeStatus.RESIGNED.value
        mock_rel_u2.save.assert_called()

        # 不应调用 delete()
        mock_rel_u2.delete.assert_not_called()

        # u2 的部门关联应被清理
        svc.emp_dept_rel_model.query.filter.assert_called()

        assert result.deleted_count == 1

    def test_resigned_employee_restored_on_resync(self):
        """之前标记离职的员工在外部重新出现时应恢复状态"""
        svc = MockSyncService()

        svc._cached_employees = [
            {"external_user_id": "u1", "name": "张三", "status": EmployeeStatus.ACTIVE.value},
        ]

        # u1 本地存在但之前被标记为离职
        mock_rel = MagicMock()
        mock_rel.external_user_id = "u1"
        mock_rel.employee_id = 1
        mock_rel.status = EmployeeStatus.RESIGNED.value

        svc.emp_org_rel_model.query.filter.return_value.all.return_value = [mock_rel]

        mock_emp = MagicMock()
        svc.employee_model.get.return_value = mock_emp

        org = MagicMock()
        org.id = 1

        result = svc.sync_employees(org)

        # 应恢复为 ACTIVE
        assert mock_rel.status == EmployeeStatus.ACTIVE.value
        assert result.updated_count == 1
        assert result.deleted_count == 0
