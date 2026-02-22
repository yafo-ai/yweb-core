"""
权限模块 - 权限服务测试

使用 Mock 模拟数据库模型，测试核心业务逻辑
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from yweb.permission.services.permission_service import PermissionService
from yweb.permission.services.role_service import RoleService
from yweb.permission.cache import PermissionCache
from yweb.permission.exceptions import (
    PermissionDeniedException,
    RoleNotFoundException,
    PermissionNotFoundException,
)


class TestPermissionService:
    """权限服务测试"""
    
    @pytest.fixture
    def mock_models(self):
        """创建模拟模型"""
        # 权限模型
        permission_model = Mock()
        permission_model.query = Mock()
        permission_model.get = Mock()
        permission_model.get_by_code = Mock()
        
        # 角色模型
        role_model = Mock()
        role_model.query = Mock()
        role_model.get = Mock()
        role_model.get_by_code = Mock()
        
        # 主体角色关联
        subject_role_model = Mock()
        subject_role_model.get_subject_roles = Mock(return_value=[])
        
        # 角色权限关联
        role_permission_model = Mock()
        role_permission_model.get_role_permission_ids = Mock(return_value=[])
        
        # 主体权限关联
        subject_permission_model = Mock()
        subject_permission_model.get_subject_permissions = Mock(return_value=[])
        
        return {
            'permission_model': permission_model,
            'role_model': role_model,
            'subject_role_model': subject_role_model,
            'role_permission_model': role_permission_model,
            'subject_permission_model': subject_permission_model,
        }
    
    @pytest.fixture
    def service(self, mock_models):
        """创建权限服务实例（禁用缓存以便测试）"""
        return PermissionService(
            **mock_models,
            use_cache=False,
        )
    
    @pytest.fixture
    def service_with_cache(self, mock_models):
        """创建带缓存的权限服务实例"""
        return PermissionService(
            **mock_models,
            use_cache=True,
        )
    
    # ==================== 权限检查测试 ====================
    
    def test_check_permission_no_roles_no_permissions(self, service, mock_models):
        """测试无角色无权限的用户"""
        # 配置 mock
        mock_models['subject_role_model'].get_subject_roles.return_value = []
        mock_models['subject_permission_model'].get_subject_permissions.return_value = []
        
        result = service.check_permission("employee:1", "user:read")
        
        assert result is False
    
    def test_check_permission_with_role_permission(self, service, mock_models):
        """测试通过角色获得权限"""
        # 模拟角色
        mock_role = Mock()
        mock_role.id = 1
        mock_role.code = "admin"
        mock_role.is_active = True
        mock_role.get_ancestors = Mock(return_value=[])
        
        mock_models['role_model'].get.return_value = mock_role
        
        # 模拟主体-角色关联
        mock_sr = Mock()
        mock_sr.role_id = 1
        mock_sr.is_valid = True
        mock_models['subject_role_model'].get_subject_roles.return_value = [mock_sr]
        
        # 模拟角色-权限关联
        mock_models['role_permission_model'].get_role_permission_ids.return_value = [10]
        
        # 模拟权限
        mock_perm = Mock()
        mock_perm.id = 10
        mock_perm.code = "user:read"
        mock_perm.is_active = True
        mock_models['permission_model'].get.return_value = mock_perm
        
        result = service.check_permission("employee:1", "user:read")
        
        assert result is True
    
    def test_check_permission_with_direct_permission(self, service, mock_models):
        """测试直接授予的权限"""
        mock_models['subject_role_model'].get_subject_roles.return_value = []
        
        # 模拟直接权限
        mock_sp = Mock()
        mock_sp.permission_id = 10
        mock_sp.is_valid = True
        mock_models['subject_permission_model'].get_subject_permissions.return_value = [mock_sp]
        
        # 模拟权限
        mock_perm = Mock()
        mock_perm.id = 10
        mock_perm.code = "special:access"
        mock_perm.is_active = True
        mock_models['permission_model'].get.return_value = mock_perm
        
        result = service.check_permission("employee:1", "special:access")
        
        assert result is True
    
    def test_check_permission_raise_exception(self, service, mock_models):
        """测试权限检查失败抛出异常"""
        mock_models['subject_role_model'].get_subject_roles.return_value = []
        mock_models['subject_permission_model'].get_subject_permissions.return_value = []
        
        with pytest.raises(PermissionDeniedException):
            service.check_permission("employee:1", "user:read", raise_exception=True)
    
    def test_check_permissions_require_all(self, service, mock_models):
        """测试检查多个权限 - 需要全部"""
        # 只有一个权限
        mock_models['subject_role_model'].get_subject_roles.return_value = []
        mock_sp = Mock()
        mock_sp.permission_id = 10
        mock_sp.is_valid = True
        mock_models['subject_permission_model'].get_subject_permissions.return_value = [mock_sp]
        
        mock_perm = Mock()
        mock_perm.id = 10
        mock_perm.code = "user:read"
        mock_perm.is_active = True
        mock_models['permission_model'].get.return_value = mock_perm
        
        # 需要两个权限，只有一个，应该失败
        result = service.check_permissions(
            "employee:1",
            ["user:read", "user:write"],
            require_all=True
        )
        
        assert result is False
    
    def test_check_permissions_require_any(self, service, mock_models):
        """测试检查多个权限 - 只需任一"""
        mock_models['subject_role_model'].get_subject_roles.return_value = []
        mock_sp = Mock()
        mock_sp.permission_id = 10
        mock_sp.is_valid = True
        mock_models['subject_permission_model'].get_subject_permissions.return_value = [mock_sp]
        
        mock_perm = Mock()
        mock_perm.id = 10
        mock_perm.code = "user:read"
        mock_perm.is_active = True
        mock_models['permission_model'].get.return_value = mock_perm
        
        # 只需任一权限
        result = service.check_permissions(
            "employee:1",
            ["user:read", "user:write"],
            require_all=False
        )
        
        assert result is True
    
    # ==================== 角色继承测试 ====================
    
    def test_role_inheritance(self, service, mock_models):
        """测试角色继承 - 子角色继承父角色权限"""
        # 模拟子角色 manager
        mock_manager = Mock()
        mock_manager.id = 2
        mock_manager.code = "manager"
        mock_manager.is_active = True
        
        # 模拟父角色 admin
        mock_admin = Mock()
        mock_admin.id = 1
        mock_admin.code = "admin"
        mock_admin.is_active = True
        
        # manager 的祖先是 admin
        mock_manager.get_ancestors = Mock(return_value=[mock_admin])
        
        def get_role(role_id):
            if role_id == 1:
                return mock_admin
            elif role_id == 2:
                return mock_manager
            return None
        
        mock_models['role_model'].get.side_effect = get_role
        mock_models['role_model'].get_by_code.side_effect = lambda code: mock_admin if code == "admin" else mock_manager
        
        # 用户有 manager 角色
        mock_sr = Mock()
        mock_sr.role_id = 2
        mock_sr.is_valid = True
        mock_models['subject_role_model'].get_subject_roles.return_value = [mock_sr]
        
        # admin 有 system:config 权限
        def get_role_perm_ids(role_id):
            if role_id == 1:  # admin
                return [100]
            return []
        mock_models['role_permission_model'].get_role_permission_ids.side_effect = get_role_perm_ids
        
        # 权限
        mock_perm = Mock()
        mock_perm.id = 100
        mock_perm.code = "system:config"
        mock_perm.is_active = True
        mock_models['permission_model'].get.return_value = mock_perm
        
        mock_models['subject_permission_model'].get_subject_permissions.return_value = []
        
        # manager 应该能继承 admin 的 system:config 权限
        result = service.check_permission("employee:1", "system:config")
        
        assert result is True


class TestPermissionServiceCache:
    """权限服务缓存集成测试"""
    
    def test_cache_hit(self):
        """测试缓存命中"""
        with patch('yweb.permission.services.permission_service.permission_cache') as mock_cache:
            mock_cache.get_permissions.return_value = {"user:read", "user:write"}
            mock_cache.has_permission.return_value = True
            
            service = PermissionService(
                permission_model=Mock(),
                role_model=Mock(),
                subject_role_model=Mock(),
                role_permission_model=Mock(),
                subject_permission_model=Mock(),
                use_cache=True,
            )
            
            result = service.check_permission("employee:1", "user:read")
            
            assert result is True
            # 验证从缓存获取
            mock_cache.has_permission.assert_called_once_with("employee:1", "user:read")
