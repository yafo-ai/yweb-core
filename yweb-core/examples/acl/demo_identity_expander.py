"""
IdentityExpander 参考实现

演示如何基于 organization + rbac 模块将用户展开为 ACL 身份标签集合。
此文件是应用层的参考代码，不在框架核心中。
"""

from yweb.acl.types import IdentityProvider


class HMindIdentityExpander(IdentityProvider):
    """将用户展开为 ACL 身份标签集合

    示例输出::

        get_identities(张三)
        → {"everyone", "user:123", "dept_only:前端部", "dept:前端部",
           "dept:技术中心", "dept:公司", "role:前端开发",
           "dept_role:前端部:前端开发"}
    """

    def __init__(self, employee_model, dept_model, dept_rel_model, role_model):
        self.Employee = employee_model
        self.Department = dept_model
        self.EmployeeDeptRel = dept_rel_model
        self.Role = role_model

    def get_identities(self, user) -> set[str]:
        identities = {"everyone", f"user:{user.id}"}

        # 查找员工记录
        employee = self.Employee.query.filter_by(user_id=user.id).first()
        if not employee:
            return identities

        # 查找部门关系
        dept_rels = self.EmployeeDeptRel.query.filter_by(
            employee_id=employee.id
        ).all()

        for rel in dept_rels:
            dept = rel.department
            # 直属部门标签
            identities.add(f"dept_only:{dept.id}")
            # 沿部门树向上，添加所有祖先部门标签
            current = dept
            while current:
                identities.add(f"dept:{current.id}")
                current = current.parent

        # RBAC 角色标签
        for role in getattr(user, "roles", []):
            identities.add(f"role:{role.code}")
            # 部门×角色 组合标签
            for rel in dept_rels:
                identities.add(f"dept_role:{rel.dept_id}:{role.code}")

        return identities


class SimpleIdentityExpander(IdentityProvider):
    """简单的身份展开器（不依赖 organization 模块）

    适用于没有组织架构的简单应用。
    """

    def get_identities(self, user) -> set[str]:
        identities = {"everyone", f"user:{user.id}"}

        # 如果用户有角色列表
        for role in getattr(user, "roles", []):
            if hasattr(role, "code"):
                identities.add(f"role:{role.code}")
            elif isinstance(role, str):
                identities.add(f"role:{role}")

        # 如果用户是管理员
        if getattr(user, "is_admin", False):
            identities.add("role:admin")

        return identities
