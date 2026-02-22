#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
组织架构模块 - 工厂函数使用示例

本文件演示如何使用 create_org_models() 工厂函数快速创建组织架构模型。
提供三种使用级别的完整示例。

================================================================================
                              三种使用级别对比
================================================================================

| 级别 | 代码量 | 灵活性 | 适用场景                    |
|------|--------|--------|---------------------------|
| 1    | ~5行   | 低     | 快速原型、零自定义           |
| 2    | ~15行  | 中     | 需要少量扩展字段             |
| 3    | ~80行  | 高     | 复杂定制需求                 |

================================================================================
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import Column, Integer, String, ForeignKey

# ============================================================================
#                          级别1：零配置快速启用
# ============================================================================

def demo_level1_zero_config():
    """
    级别1：零配置快速启用
    
    适用场景：
    - 快速原型开发
    - 不需要自定义字段
    - 希望最少代码启用功能
    """
    print("\n" + "=" * 60)
    print("级别1：零配置快速启用")
    print("=" * 60)
    
    from yweb.organization import create_org_models
    
    # 一行创建所有模型
    org = create_org_models(table_prefix="demo1_")
    
    # 查看生成的模型
    print(f"\n[OK] Organization: {org.Organization.__tablename__}")
    print(f"[OK] Department: {org.Department.__tablename__}")
    print(f"[OK] Employee: {org.Employee.__tablename__}")
    print(f"[OK] EmployeeOrgRel: {org.EmployeeOrgRel.__tablename__}")
    print(f"[OK] EmployeeDeptRel: {org.EmployeeDeptRel.__tablename__}")
    print(f"[OK] DepartmentLeader: {org.DepartmentLeader.__tablename__}")
    
    # 查看自动设置的 relationship
    print(f"\n[OK] Department.organization: {hasattr(org.Department, 'organization')}")
    print(f"[OK] Department.children: {hasattr(org.Department, 'children')}")
    print(f"[OK] Employee.primary_org: {hasattr(org.Employee, 'primary_org')}")
    
    # 可以直接用于 API 路由
    print("\n用于 create_org_router() 的参数：")
    print(org.as_dict())
    
    return org


# ============================================================================
#                     级别2：轻量自定义（通过 Mixin）
# ============================================================================

def demo_level2_with_mixin():
    """
    级别2：轻量自定义（通过 Mixin 扩展字段）
    
    适用场景：
    - 需要添加少量自定义字段（如关联用户）
    - 不需要修改模型结构
    - 希望保持简洁
    """
    print("\n" + "=" * 60)
    print("级别2：轻量自定义（通过 Mixin）")
    print("=" * 60)
    
    from yweb.organization import create_org_models
    from yweb.orm import fields, BaseModel
    
    # 假设有一个 User 模型
    class User(BaseModel):
        __tablename__ = "demo2_user"
        __table_args__ = {"extend_existing": True}
        
        username = Column(String(50))
    
    # 定义 Mixin 添加自定义字段
    class EmployeeUserMixin:
        """员工关联用户账号"""
        # 使用 fields.OneToOne 自动创建 user_id 列和 relationship
        user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)
    
    # 创建模型时传入 Mixin
    org = create_org_models(
        table_prefix="demo2_",
        employee_mixin=EmployeeUserMixin,
    )
    
    print(f"\n[OK] Employee tablename: {org.Employee.__tablename__}")
    print(f"[OK] Employee has 'user' attr: {hasattr(org.Employee, 'user')}")
    
    # 检查 fields.ManyToOne 是否被处理
    # 注意：fields.* 在类定义后由 BaseModel.__init_subclass__ 自动处理
    
    return org


def demo_level2_with_customizer():
    """
    级别2 变体：使用 customizer 回调添加自定义逻辑
    
    适用场景：
    - 需要动态设置属性
    - 需要在模型创建后执行额外逻辑
    """
    print("\n" + "=" * 60)
    print("级别2 变体：使用 customizer 回调")
    print("=" * 60)
    
    from yweb.organization import create_org_models
    
    def customize_organization(cls):
        """自定义组织模型"""
        # 添加自定义方法
        def get_display_name(self):
            return f"[{self.code}] {self.name}" if self.code else self.name
        
        cls.get_display_name = get_display_name
        print(f"  [OK] Added get_display_name method to {cls.__name__}")
    
    def customize_employee(cls):
        """自定义员工模型"""
        # 添加类属性
        cls.DEFAULT_AVATAR = "/static/default-avatar.png"
        print(f"  [OK] Added DEFAULT_AVATAR attr to {cls.__name__}")
    
    org = create_org_models(
        table_prefix="demo2c_",
        organization_customizer=customize_organization,
        employee_customizer=customize_employee,
    )
    
    print(f"\n[OK] Organization.get_display_name: {hasattr(org.Organization, 'get_display_name')}")
    print(f"[OK] Employee.DEFAULT_AVATAR: {getattr(org.Employee, 'DEFAULT_AVATAR', None)}")
    
    return org


# ============================================================================
#                          级别3：完全自定义
# ============================================================================

def demo_level3_full_custom():
    """
    级别3：完全自定义（继承抽象类）
    
    适用场景：
    - 需要完全控制模型定义
    - 有复杂的自定义需求
    - 需要自定义 relationship 配置
    """
    print("\n" + "=" * 60)
    print("级别3：完全自定义（继承抽象类）")
    print("=" * 60)
    
    from yweb.organization import (
        AbstractOrganization,
        AbstractDepartment,
        AbstractEmployee,
        AbstractEmployeeOrgRel,
        AbstractEmployeeDeptRel,
        AbstractDepartmentLeader,
        setup_org_relationships,
    )
    from yweb.orm import BaseModel
    from sqlalchemy.orm import Mapped, mapped_column
    
    # 定义表名前缀
    PREFIX = "demo3_"
    
    class Organization(AbstractOrganization):
        __tablename__ = f"{PREFIX}organization"
        __table_args__ = {"extend_existing": True}
        
        # 自定义字段
        license_no: Mapped[str] = mapped_column(String(50), nullable=True, comment="营业执照号")
    
    class Department(AbstractDepartment):
        __tablename__ = f"{PREFIX}department"
        __org_tablename__ = f"{PREFIX}organization"
        __employee_tablename__ = f"{PREFIX}employee"
        __table_args__ = {"extend_existing": True}
        
        # 自定义字段
        budget: Mapped[int] = mapped_column(Integer, default=0, comment="部门预算")
    
    class Employee(AbstractEmployee):
        __tablename__ = f"{PREFIX}employee"
        __org_tablename__ = f"{PREFIX}organization"
        __dept_tablename__ = f"{PREFIX}department"
        __table_args__ = {"extend_existing": True}
        
        # 自定义字段
        id_card: Mapped[str] = mapped_column(String(18), nullable=True, comment="身份证号")
    
    class EmployeeOrgRel(AbstractEmployeeOrgRel):
        __tablename__ = f"{PREFIX}employee_org_rel"
        __employee_tablename__ = f"{PREFIX}employee"
        __org_tablename__ = f"{PREFIX}organization"
        __table_args__ = {"extend_existing": True}
    
    class EmployeeDeptRel(AbstractEmployeeDeptRel):
        __tablename__ = f"{PREFIX}employee_dept_rel"
        __employee_tablename__ = f"{PREFIX}employee"
        __dept_tablename__ = f"{PREFIX}department"
        __table_args__ = {"extend_existing": True}
    
    class DepartmentLeader(AbstractDepartmentLeader):
        __tablename__ = f"{PREFIX}department_leader"
        __dept_tablename__ = f"{PREFIX}department"
        __employee_tablename__ = f"{PREFIX}employee"
        __table_args__ = {"extend_existing": True}
    
    # 设置 relationship
    setup_org_relationships(
        Organization, Department, Employee,
        EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
    )
    
    print(f"\n[OK] Organization.license_no: {hasattr(Organization, 'license_no')}")
    print(f"[OK] Department.budget: {hasattr(Department, 'budget')}")
    print(f"[OK] Employee.id_card: {hasattr(Employee, 'id_card')}")
    print(f"[OK] Department.organization: {hasattr(Department, 'organization')}")
    
    return {
        "Organization": Organization,
        "Department": Department,
        "Employee": Employee,
        "EmployeeOrgRel": EmployeeOrgRel,
        "EmployeeDeptRel": EmployeeDeptRel,
        "DepartmentLeader": DepartmentLeader,
    }


# ============================================================================
#                          API 路由集成示例
# ============================================================================

def demo_api_integration():
    """
    演示如何将工厂创建的模型与 API 路由集成
    """
    print("\n" + "=" * 60)
    print("API 路由集成示例")
    print("=" * 60)
    
    from yweb.organization import create_org_models, create_org_router
    
    # 创建模型
    org = create_org_models(table_prefix="api_demo_")
    
    # 创建路由（这里只是演示，实际需要在 FastAPI 应用中使用）
    router = create_org_router(
        **org.as_dict(),
        prefix="/org",
        tags=["组织架构"],
        # dependencies=[Depends(get_current_user)],  # 实际使用时添加
    )
    
    print(f"\n[OK] Router created, routes:")
    for route in router.routes:
        if hasattr(route, 'path'):
            print(f"  - {route.methods} {route.path}")


# ============================================================================
#                              主函数
# ============================================================================

def main():
    """运行所有示例"""
    print("\n" + "=" * 70)
    print("   组织架构模块 - create_org_models() 工厂函数使用示例")
    print("=" * 70)
    
    # 级别1
    demo_level1_zero_config()
    
    # 级别2
    demo_level2_with_mixin()
    demo_level2_with_customizer()
    
    # 级别3
    demo_level3_full_custom()
    
    # API 集成
    demo_api_integration()
    
    print("\n" + "=" * 70)
    print("   所有示例运行完成！")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
