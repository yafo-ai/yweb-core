"""
FastAPI 集成演示

演示：
1. 在 FastAPI 中初始化权限服务
2. 使用依赖注入进行权限检查
3. 使用装饰器进行权限检查
4. 挂载管理 API

运行方式:
    uvicorn demo_fastapi_integration:app --reload
    
然后访问:
    http://localhost:8000/docs
"""

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import List

from yweb.orm import init_database, get_engine
from yweb.orm.core_model import CoreModel
from yweb.permission.models import (
    AbstractPermission,
    AbstractRole,
    AbstractSubjectRole,
    AbstractRolePermission,
    AbstractSubjectPermission,
)
from yweb.permission import (
    init_permission_dependency,
    get_permission_service,
    require_permission,
    require_role,
    create_permission_router,
)
from yweb.auth import UserIdentity


# ==================== 定义模型 ====================

class Permission(AbstractPermission):
    __tablename__ = "fastapi_permission"


class Role(AbstractRole):
    __tablename__ = "fastapi_role"
    __role_tablename__ = "fastapi_role"


class SubjectRole(AbstractSubjectRole):
    __tablename__ = "fastapi_subject_role"
    __role_tablename__ = "fastapi_role"


class RolePermission(AbstractRolePermission):
    __tablename__ = "fastapi_role_permission"
    __role_tablename__ = "fastapi_role"
    __permission_tablename__ = "fastapi_permission"


class SubjectPermission(AbstractSubjectPermission):
    __tablename__ = "fastapi_subject_permission"
    __permission_tablename__ = "fastapi_permission"


# ==================== 创建 FastAPI 应用 ====================

app = FastAPI(
    title="权限模块 FastAPI 集成演示",
    description="演示如何在 FastAPI 中使用权限模块",
    version="1.0.0",
)


# ==================== 模拟用户数据 ====================

MOCK_USERS = {
    "token_admin": {"user_id": 1, "username": "admin", "source": "employee"},
    "token_user": {"user_id": 2, "username": "user", "source": "employee"},
    "token_guest": {"user_id": 3, "username": "guest", "source": "external"},
}


def mock_get_current_user(token: str = None) -> UserIdentity:
    """模拟获取当前用户（实际应从 JWT 等获取）"""
    if not token or token not in MOCK_USERS:
        raise HTTPException(status_code=401, detail="未认证")
    
    user_data = MOCK_USERS[token]
    return UserIdentity(
        user_id=user_data["user_id"],
        username=user_data["username"],
        source=user_data["source"],
    )


# ==================== 初始化 ====================

@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # 1. 初始化数据库（保存在脚本所在目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_fastapi_permission.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}")
    
    # 设置 query 属性
    CoreModel.query = session_scope.query_property()
    
    # 创建表
    CoreModel.metadata.drop_all(engine)
    CoreModel.metadata.create_all(engine)
    print(f"✓ 数据库: {db_path}")
    
    # 2. 初始化权限服务
    init_permission_dependency(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
    )
    
    # 3. 初始化演示数据
    await init_demo_data()


async def init_demo_data():
    """初始化演示数据"""
    from yweb.permission.services import PermissionService, RoleService
    
    perm_service = PermissionService(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
    )
    
    role_service = RoleService(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    )
    
    # 检查是否已有数据
    if Permission.query.first():
        return
    
    # 创建权限
    permissions = [
        ("user:list", "用户列表"),
        ("user:read", "查看用户"),
        ("user:write", "编辑用户"),
        ("user:delete", "删除用户"),
        ("admin:config", "系统配置"),
    ]
    for code, name in permissions:
        perm_service.create_permission(code=code, name=name)
    
    # 创建角色
    role_service.create_role(code="admin", name="管理员", is_system=True)
    role_service.create_role(code="user", name="普通用户")
    role_service.create_role(code="guest", name="访客")
    
    # 设置角色权限
    role_service.set_role_permissions("admin", [
        "user:list", "user:read", "user:write", "user:delete", "admin:config"
    ])
    role_service.set_role_permissions("user", ["user:list", "user:read"])
    role_service.set_role_permissions("guest", ["user:list"])
    
    # 分配角色
    perm_service.assign_role("employee:1", "admin")
    perm_service.assign_role("employee:2", "user")
    perm_service.assign_role("external:3", "guest")
    
    print("✓ 演示数据初始化完成")


# ==================== API 路由 ====================

@app.get("/")
async def root():
    """首页"""
    return {
        "message": "权限模块 FastAPI 集成演示",
        "usage": {
            "step1": "使用不同的 token 参数模拟不同用户",
            "step2": "token_admin = 管理员 (拥有所有权限)",
            "step3": "token_user = 普通用户 (只有查看权限)",
            "step4": "token_guest = 访客 (只有列表权限)",
        },
        "endpoints": [
            "GET /users?token=xxx - 用户列表 (需要 user:list)",
            "GET /users/{id}?token=xxx - 用户详情 (需要 user:read)",
            "DELETE /users/{id}?token=xxx - 删除用户 (需要 admin 角色)",
            "GET /admin/config?token=xxx - 系统配置 (需要 admin:config)",
        ]
    }


# 模拟用户数据
USERS_DB = [
    {"id": 1, "name": "张三", "email": "zhang@example.com"},
    {"id": 2, "name": "李四", "email": "li@example.com"},
    {"id": 3, "name": "王五", "email": "wang@example.com"},
]


@app.get("/users")
async def list_users(token: str = None):
    """用户列表 - 需要 user:list 权限"""
    user = mock_get_current_user(token)
    
    # 获取 subject_id
    subject_id = f"{user.source}:{user.user_id}"
    
    # 检查权限
    perm_service = get_permission_service()
    if not perm_service.check_permission(subject_id, "user:list"):
        raise HTTPException(status_code=403, detail="权限不足: user:list")
    
    return {
        "current_user": user.username,
        "users": USERS_DB
    }


@app.get("/users/{user_id}")
async def get_user(user_id: int, token: str = None):
    """用户详情 - 需要 user:read 权限"""
    user = mock_get_current_user(token)
    subject_id = f"{user.source}:{user.user_id}"
    
    perm_service = get_permission_service()
    if not perm_service.check_permission(subject_id, "user:read"):
        raise HTTPException(status_code=403, detail="权限不足: user:read")
    
    # 查找用户
    for u in USERS_DB:
        if u["id"] == user_id:
            return {"current_user": user.username, "user": u}
    
    raise HTTPException(status_code=404, detail="用户不存在")


@app.delete("/users/{user_id}")
async def delete_user(user_id: int, token: str = None):
    """删除用户 - 需要 admin 角色"""
    user = mock_get_current_user(token)
    subject_id = f"{user.source}:{user.user_id}"
    
    perm_service = get_permission_service()
    
    # 检查角色
    if not perm_service.check_role(subject_id, "admin"):
        raise HTTPException(status_code=403, detail="需要 admin 角色")
    
    return {
        "current_user": user.username,
        "message": f"用户 {user_id} 已删除（模拟）"
    }


@app.get("/admin/config")
async def get_config(token: str = None):
    """系统配置 - 需要 admin:config 权限"""
    user = mock_get_current_user(token)
    subject_id = f"{user.source}:{user.user_id}"
    
    perm_service = get_permission_service()
    if not perm_service.check_permission(subject_id, "admin:config"):
        raise HTTPException(status_code=403, detail="权限不足: admin:config")
    
    return {
        "current_user": user.username,
        "config": {
            "site_name": "演示站点",
            "max_users": 1000,
            "debug": False,
        }
    }


@app.get("/my-permissions")
async def my_permissions(token: str = None):
    """查看当前用户的所有权限"""
    user = mock_get_current_user(token)
    subject_id = f"{user.source}:{user.user_id}"
    
    perm_service = get_permission_service()
    roles = perm_service.get_all_roles(subject_id)
    permissions = perm_service.get_all_permissions(subject_id)
    
    return {
        "user": user.username,
        "subject_id": subject_id,
        "roles": list(roles),
        "permissions": list(permissions),
    }


# ==================== 运行提示 ====================

if __name__ == "__main__":
    print("""
    运行方式:
        uvicorn demo_fastapi_integration:app --reload
    
    然后访问:
        http://localhost:8000/docs
    
    测试示例:
        GET http://localhost:8000/users?token=token_admin
        GET http://localhost:8000/users?token=token_user
        GET http://localhost:8000/users?token=token_guest
        DELETE http://localhost:8000/users/1?token=token_admin  # 成功
        DELETE http://localhost:8000/users/1?token=token_user   # 403
    """)
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
