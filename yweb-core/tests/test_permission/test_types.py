"""
权限模块 - 类型工具测试
"""

import pytest
from yweb.permission.types import (
    parse_subject_id,
    make_subject_id,
    make_permission_code,
    parse_permission_code,
)
from yweb.permission.enums import UserType


class TestSubjectId:
    """主体ID工具函数测试"""
    
    def test_make_subject_id_with_enum(self):
        """测试使用枚举创建主体ID"""
        result = make_subject_id(UserType.EMPLOYEE, 123)
        assert result == "employee:123"
    
    def test_make_subject_id_with_string(self):
        """测试使用字符串创建主体ID"""
        result = make_subject_id("external", 456)
        assert result == "external:456"
    
    def test_parse_subject_id_valid(self):
        """测试解析有效的主体ID"""
        subject_type, subject_id = parse_subject_id("employee:123")
        assert subject_type == "employee"
        assert subject_id == 123
    
    def test_parse_subject_id_invalid_format(self):
        """测试解析无效格式的主体ID"""
        with pytest.raises(ValueError, match="Invalid subject_id format"):
            parse_subject_id("invalid")
    
    def test_parse_subject_id_invalid_id(self):
        """测试解析非数字ID"""
        with pytest.raises(ValueError, match="id part must be integer"):
            parse_subject_id("employee:abc")


class TestPermissionCode:
    """权限编码工具函数测试"""
    
    def test_make_permission_code(self):
        """测试创建权限编码"""
        result = make_permission_code("user", "read")
        assert result == "user:read"
    
    def test_parse_permission_code(self):
        """测试解析权限编码"""
        resource, action = parse_permission_code("user:read")
        assert resource == "user"
        assert action == "read"
    
    def test_parse_permission_code_with_colon_in_action(self):
        """测试解析包含冒号的权限编码"""
        resource, action = parse_permission_code("api:user:read")
        assert resource == "api"
        assert action == "user:read"
    
    def test_parse_permission_code_invalid(self):
        """测试解析无效的权限编码"""
        with pytest.raises(ValueError):
            parse_permission_code("invalid")
