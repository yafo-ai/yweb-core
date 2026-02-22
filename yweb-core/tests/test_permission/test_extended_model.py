"""
权限模块 - 扩展模型字段测试

测试用户继承抽象模型并添加自定义字段时，API 响应是否能正确包含这些扩展字段。

测试内容：
1. to_dict() 是否包含扩展字段
2. Schema (extra="allow") 是否能正确处理扩展字段
3. API 响应是否包含扩展字段
"""

import pytest
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import BaseModel, CoreModel
from yweb.permission.models import (
    AbstractPermission,
    AbstractRole,
)
from yweb.permission.schemas.permission import PermissionResponse
from yweb.permission.schemas.role import RoleResponse


# ==================== 扩展模型定义（模拟用户场景） ====================

class ExtendedPermission(AbstractPermission):
    """扩展的权限模型 - 添加自定义字段"""
    __tablename__ = "test_ext_permission"
    __table_args__ = {'extend_existing': True}
    
    # 用户添加的扩展字段
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="关联部门ID"
    )
    
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="优先级"
    )
    
    custom_tag: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="自定义标签"
    )


class ExtendedRole(AbstractRole):
    """扩展的角色模型 - 添加自定义字段"""
    __tablename__ = "test_ext_role"
    __role_tablename__ = "test_ext_role"
    __table_args__ = {'extend_existing': True}
    
    # 用户添加的扩展字段
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="所属部门ID"
    )
    
    max_users: Mapped[int] = mapped_column(
        Integer,
        default=100,
        comment="最大用户数"
    )
    
    color: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="角色颜色标识"
    )


# ==================== to_dict() 集成测试 ====================

class TestToDictWithExtendedFields:
    """测试 to_dict() 包含扩展字段（需要数据库）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_permission_to_dict_includes_extended_fields(self):
        """测试 Permission 的 to_dict() 包含扩展字段"""
        # 创建带扩展字段的权限
        perm = ExtendedPermission(
            code="test:read",
            name="测试读取",
            resource="test",
            action="read",
            # 扩展字段
            department_id=5,
            priority=10,
            custom_tag="important",
        )
        perm.add(commit=True)
        
        # 获取 to_dict()
        data = perm.to_dict()
        
        # 验证核心字段
        assert data["code"] == "test:read"
        assert data["name"] == "测试读取"
        assert data["resource"] == "test"
        assert data["action"] == "read"
        
        # 验证扩展字段
        assert data["department_id"] == 5
        assert data["priority"] == 10
        assert data["custom_tag"] == "important"
    
    def test_role_to_dict_includes_extended_fields(self):
        """测试 Role 的 to_dict() 包含扩展字段"""
        # 创建带扩展字段的角色
        role = ExtendedRole(
            code="test_admin",
            name="测试管理员",
            # 扩展字段
            department_id=3,
            max_users=50,
            color="#FF5500",
        )
        role.add(commit=True)
        
        # 获取 to_dict()
        data = role.to_dict()
        
        # 验证核心字段
        assert data["code"] == "test_admin"
        assert data["name"] == "测试管理员"
        
        # 验证扩展字段
        assert data["department_id"] == 3
        assert data["max_users"] == 50
        assert data["color"] == "#FF5500"
    
    def test_extended_fields_with_null_values(self):
        """测试扩展字段为 NULL 时的 to_dict()"""
        perm = ExtendedPermission(
            code="test:null",
            name="测试空值",
            resource="test",
            action="null",
            # 扩展字段为 NULL
            department_id=None,
            custom_tag=None,
        )
        perm.add(commit=True)
        
        data = perm.to_dict()
        
        # NULL 值也应该包含在 dict 中
        assert "department_id" in data
        assert data["department_id"] is None
        assert "custom_tag" in data
        assert data["custom_tag"] is None
        # 有默认值的字段
        assert data["priority"] == 0


# ==================== Schema 测试（不需要数据库） ====================

class TestSchemaExtraAllow:
    """测试 Schema 的 extra='allow' 配置"""
    
    def test_permission_response_accepts_extra_fields(self):
        """测试 PermissionResponse 接受额外字段"""
        # 模拟 to_dict() 返回的数据（包含扩展字段）
        data = {
            "id": 1,
            "code": "test:read",
            "name": "测试读取",
            "resource": "test",
            "action": "read",
            "description": None,
            "module": None,
            "is_active": True,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "department_id": 5,
            "priority": 10,
            "custom_tag": "important",
        }
        
        # 创建 Schema 实例
        response = PermissionResponse(**data)
        
        # 验证核心字段
        assert response.code == "test:read"
        assert response.name == "测试读取"
        
        # 验证扩展字段通过 model_dump() 返回
        dumped = response.model_dump()
        assert dumped["department_id"] == 5
        assert dumped["priority"] == 10
        assert dumped["custom_tag"] == "important"
    
    def test_role_response_accepts_extra_fields(self):
        """测试 RoleResponse 接受额外字段"""
        data = {
            "id": 1,
            "code": "admin",
            "name": "管理员",
            "description": "系统管理员",
            "parent_id": None,
            "is_active": True,
            "is_system": True,
            "level": 1,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "department_id": 3,
            "max_users": 50,
            "color": "#FF5500",
        }
        
        response = RoleResponse(**data)
        
        # 验证核心字段
        assert response.code == "admin"
        assert response.name == "管理员"
        
        # 验证扩展字段
        dumped = response.model_dump()
        assert dumped["department_id"] == 3
        assert dumped["max_users"] == 50
        assert dumped["color"] == "#FF5500"
    
    def test_schema_model_dump_preserves_extra_fields(self):
        """测试 model_dump() 保留额外字段"""
        data = {
            "id": 1,
            "code": "test",
            "name": "测试",
            "resource": "test",
            "action": "test",
            "description": None,
            "module": None,
            "is_active": True,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
            # 多个扩展字段
            "custom_field_1": "value1",
            "custom_field_2": 123,
            "custom_field_3": True,
            "custom_field_4": ["a", "b", "c"],
        }
        
        response = PermissionResponse(**data)
        dumped = response.model_dump()
        
        # 所有扩展字段都应该保留
        assert dumped["custom_field_1"] == "value1"
        assert dumped["custom_field_2"] == 123
        assert dumped["custom_field_3"] is True
        assert dumped["custom_field_4"] == ["a", "b", "c"]


# ==================== API 流程集成测试 ====================

class TestAPIWithExtendedModel:
    """测试完整的 API 流程：模型 -> to_dict() -> Schema -> 响应"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_api_response_includes_extended_fields(self):
        """测试完整流程：模型 -> to_dict() -> Schema -> API 响应"""
        # 1. 创建扩展模型实例
        perm = ExtendedPermission(
            code="api:test",
            name="API测试",
            resource="api",
            action="test",
            department_id=7,
            priority=5,
            custom_tag="api-test",
        )
        perm.add(commit=True)
        
        # 2. 获取 to_dict()
        data = perm.to_dict()
        
        # 3. 通过 Schema 包装（模拟 API 实现）
        response_data = PermissionResponse(**data).model_dump()
        
        # 4. 验证响应包含所有字段
        assert response_data["code"] == "api:test"
        assert response_data["name"] == "API测试"
        assert response_data["department_id"] == 7
        assert response_data["priority"] == 5
        assert response_data["custom_tag"] == "api-test"
    
    def test_list_api_includes_extended_fields(self):
        """测试列表 API 响应包含扩展字段"""
        # 创建多个带扩展字段的权限
        perms = []
        for i in range(3):
            perm = ExtendedPermission(
                code=f"list:test:{i}",
                name=f"列表测试{i}",
                resource="list",
                action=f"test{i}",
                department_id=i + 1,
                priority=i * 10,
                custom_tag=f"tag-{i}",
            )
            perm.add(commit=True)
            perms.append(perm)
        
        # 模拟列表 API 的响应构建
        items = [PermissionResponse(**p.to_dict()).model_dump() for p in perms]
        
        # 验证每个项都包含扩展字段
        for i, item in enumerate(items):
            assert item["code"] == f"list:test:{i}"
            assert item["department_id"] == i + 1
            assert item["priority"] == i * 10
            assert item["custom_tag"] == f"tag-{i}"


# ==================== 边界情况测试 ====================

class TestEdgeCases:
    """边界情况测试"""
    
    def test_schema_with_nested_extra_fields(self):
        """测试 Schema 处理嵌套的额外字段"""
        data = {
            "id": 1,
            "code": "nested:test",
            "name": "嵌套测试",
            "resource": "nested",
            "action": "test",
            "description": None,
            "module": None,
            "is_active": True,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
            # 嵌套结构的扩展字段
            "metadata": {
                "created_by": "admin",
                "tags": ["a", "b"],
            },
        }
        
        response = PermissionResponse(**data)
        dumped = response.model_dump()
        
        assert dumped["metadata"]["created_by"] == "admin"
        assert dumped["metadata"]["tags"] == ["a", "b"]
    
    def test_schema_with_datetime_extra_field(self):
        """测试 Schema 处理 datetime 类型的额外字段"""
        custom_time = datetime(2026, 1, 25, 10, 30, 0)
        
        data = {
            "id": 1,
            "code": "time:test",
            "name": "时间测试",
            "resource": "time",
            "action": "test",
            "description": None,
            "module": None,
            "is_active": True,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
            # datetime 类型的扩展字段
            "effective_from": custom_time,
        }
        
        response = PermissionResponse(**data)
        dumped = response.model_dump()
        
        assert dumped["effective_from"] == custom_time
    
    def test_model_config_is_correct(self):
        """验证 Schema 的 model_config 配置正确"""
        # PermissionResponse
        assert hasattr(PermissionResponse, 'model_config')
        config = PermissionResponse.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True
        
        # RoleResponse
        assert hasattr(RoleResponse, 'model_config')
        config = RoleResponse.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True


# ==================== 性能测试 ====================

class TestPerformance:
    """性能相关测试"""
    
    def test_large_number_of_extra_fields(self):
        """测试大量扩展字段的处理"""
        # 构建包含 50 个扩展字段的数据
        data = {
            "id": 1,
            "code": "perf:test",
            "name": "性能测试",
            "resource": "perf",
            "action": "test",
            "description": None,
            "module": None,
            "is_active": True,
            "sort_order": 0,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        
        # 添加 50 个扩展字段
        for i in range(50):
            data[f"extra_field_{i}"] = f"value_{i}"
        
        # 创建 Schema 实例
        response = PermissionResponse(**data)
        dumped = response.model_dump()
        
        # 验证所有扩展字段都存在
        for i in range(50):
            assert dumped[f"extra_field_{i}"] == f"value_{i}"
    
    def test_batch_processing_with_extra_fields(self):
        """测试批量处理扩展字段"""
        # 创建 100 个数据项
        items = []
        for i in range(100):
            data = {
                "id": i,
                "code": f"batch:{i}",
                "name": f"批量测试{i}",
                "resource": "batch",
                "action": str(i),
                "description": None,
                "module": None,
                "is_active": True,
                "sort_order": i,
                "created_at": datetime.now(),
                "updated_at": None,
                # 扩展字段
                "batch_id": i,
                "batch_group": i // 10,
            }
            items.append(data)
        
        # 批量处理
        results = [PermissionResponse(**item).model_dump() for item in items]
        
        # 验证结果
        assert len(results) == 100
        for i, result in enumerate(results):
            assert result["batch_id"] == i
            assert result["batch_group"] == i // 10
