"""
权限模块 - 异常测试
"""

import pytest
from yweb.permission.exceptions import (
    PermissionException,
    PermissionDeniedException,
    RoleNotFoundException,
    PermissionNotFoundException,
    DuplicateRoleException,
    RoleInheritanceCycleException,
    SystemRoleModifyException,
)


class TestPermissionExceptions:
    """权限异常测试"""
    
    def test_permission_denied_basic(self):
        """测试权限拒绝异常 - 基本"""
        exc = PermissionDeniedException()
        
        assert exc.status_code == 403
        assert "权限不足" in exc.message
    
    def test_permission_denied_with_details(self):
        """测试权限拒绝异常 - 带详情"""
        exc = PermissionDeniedException(
            permission_code="user:delete",
            subject_id="employee:1",
            required_permissions=["user:delete"],
        )
        
        assert exc.status_code == 403
        assert exc.permission_code == "user:delete"
        assert exc.subject_id == "employee:1"
        assert any("user:delete" in d for d in exc.details)
    
    def test_role_not_found(self):
        """测试角色不存在异常"""
        exc = RoleNotFoundException("admin")
        
        assert exc.status_code == 404
        assert exc.role_code == "admin"
        assert "admin" in exc.message
    
    def test_permission_not_found(self):
        """测试权限不存在异常"""
        exc = PermissionNotFoundException("user:delete")
        
        assert exc.status_code == 404
        assert exc.permission_code == "user:delete"
    
    def test_duplicate_role(self):
        """测试角色已存在异常"""
        exc = DuplicateRoleException("admin")
        
        assert exc.status_code == 409
        assert exc.role_code == "admin"
    
    def test_role_inheritance_cycle(self):
        """测试角色继承循环异常"""
        exc = RoleInheritanceCycleException("manager", "admin")
        
        assert exc.status_code == 400
        assert exc.role_code == "manager"
        assert exc.parent_code == "admin"
    
    def test_system_role_modify(self):
        """测试系统角色修改异常"""
        exc = SystemRoleModifyException("super_admin", "删除")
        
        assert exc.status_code == 403
        assert exc.role_code == "super_admin"
        assert "删除" in exc.message
