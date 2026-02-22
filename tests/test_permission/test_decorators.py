"""
权限模块 - 装饰器测试
"""

import pytest
from unittest.mock import Mock, patch

from yweb.permission.decorators import permission_required, role_required
from yweb.permission.exceptions import PermissionDeniedException


class TestPermissionDecorator:
    """权限检查装饰器测试"""
    
    def test_permission_required_pass(self):
        """测试权限检查通过"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.check_permissions.return_value = True
            mock_get_service.return_value = mock_service
            
            @permission_required("user:read")
            def my_func(subject_id: str):
                return "success"
            
            result = my_func(subject_id="employee:1")
            
            assert result == "success"
            mock_service.check_permissions.assert_called_once()
    
    def test_permission_required_denied(self):
        """测试权限检查失败"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.check_permissions.return_value = False
            mock_get_service.return_value = mock_service
            
            @permission_required("user:delete")
            def my_func(subject_id: str):
                return "success"
            
            with pytest.raises(PermissionDeniedException):
                my_func(subject_id="employee:1")
    
    def test_permission_required_multiple_permissions(self):
        """测试多个权限检查"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.check_permissions.return_value = True
            mock_get_service.return_value = mock_service
            
            @permission_required("user:read", "user:write", require_all=True)
            def my_func(subject_id: str):
                return "success"
            
            result = my_func(subject_id="employee:1")
            
            assert result == "success"
            mock_service.check_permissions.assert_called_with(
                subject_id="employee:1",
                permission_codes=["user:read", "user:write"],
                require_all=True
            )
    
    def test_permission_required_custom_param_name(self):
        """测试自定义参数名"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.check_permissions.return_value = True
            mock_get_service.return_value = mock_service
            
            @permission_required("user:read", subject_id_param="current_user")
            def my_func(current_user: str, data: dict):
                return "success"
            
            result = my_func(current_user="employee:1", data={})
            
            assert result == "success"
    
    def test_permission_required_missing_subject_id(self):
        """测试缺少 subject_id 参数"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_get_service.return_value = mock_service
            
            @permission_required("user:read")
            def my_func(other_param: str):
                return "success"
            
            with pytest.raises(PermissionDeniedException, match="无法获取用户标识"):
                my_func(other_param="value")


class TestRoleDecorator:
    """角色检查装饰器测试"""
    
    def test_role_required_pass(self):
        """测试角色检查通过"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_all_roles.return_value = {"admin", "manager"}
            mock_get_service.return_value = mock_service
            
            @role_required("admin")
            def my_func(subject_id: str):
                return "success"
            
            result = my_func(subject_id="employee:1")
            
            assert result == "success"
    
    def test_role_required_denied(self):
        """测试角色检查失败"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_all_roles.return_value = {"user"}  # 只有 user 角色
            mock_get_service.return_value = mock_service
            
            @role_required("admin")
            def my_func(subject_id: str):
                return "success"
            
            with pytest.raises(PermissionDeniedException, match="角色不足"):
                my_func(subject_id="employee:1")
    
    def test_role_required_any(self):
        """测试只需任一角色"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_all_roles.return_value = {"manager"}  # 只有 manager
            mock_get_service.return_value = mock_service
            
            @role_required("admin", "manager", require_all=False)
            def my_func(subject_id: str):
                return "success"
            
            result = my_func(subject_id="employee:1")
            
            assert result == "success"
    
    def test_role_required_all(self):
        """测试需要全部角色"""
        with patch('yweb.permission.decorators.get_permission_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_all_roles.return_value = {"manager"}  # 只有 manager
            mock_get_service.return_value = mock_service
            
            @role_required("admin", "manager", require_all=True)
            def my_func(subject_id: str):
                return "success"
            
            with pytest.raises(PermissionDeniedException):
                my_func(subject_id="employee:1")
