"""
YWeb 示例应用

演示如何使用基础库的各种功能
"""

from fastapi import FastAPI
from yweb import (
    OK, BadRequest, NotFound, Warning,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    PerformanceMonitoringMiddleware,
    Page,
    PaginationField,
    setup_logger,
    hash_password,
    verify_password,
)

# 配置日志
logger = setup_logger("demo_app", level="INFO", console=True)

# 创建FastAPI应用
app = FastAPI(
    title="YWeb Demo",
    description="演示基础类库的使用",
    version="0.1.0"
)

# 添加中间件
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    RequestLoggingMiddleware,
    max_body_size=1024 * 1024 * 5,
    skip_paths={"/health", "/metrics"}
)
app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_request_threshold=1.0
)

# 模拟数据库
USERS = {
    1: {"id": 1, "name": "Tom", "email": "tom@example.com"},
    2: {"id": 2, "name": "Jerry", "email": "jerry@example.com"},
    3: {"id": 3, "name": "Alice", "email": "alice@example.com"},
}


@app.on_event("startup")
def startup_event():
    logger.info("Demo application is starting up...")


@app.on_event("shutdown")
def shutdown_event():
    logger.info("Demo application is shutting down...")


@app.get("/")
def read_root():
    """根路径"""
    return OK(
        {
            "app": "YWeb Demo",
            "version": "0.1.0",
            "endpoints": [
                "/users - 获取用户列表（支持分页）",
                "/users/{user_id} - 获取单个用户",
                "/users (POST) - 创建用户",
                "/auth/login - 登录示例",
                "/health - 健康检查",
            ]
        },
        "欢迎使用 YWeb"
    )


@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/users")
def list_users(pagination: PaginationField):
    """获取用户列表（分页）"""
    users_list = list(USERS.values())
    total = len(users_list)
    
    # 分页处理
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    page_users = users_list[start:end]
    
    page_result = Page(
        rows=page_users,
        total_records=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )
    
    logger.info(f"查询用户列表，页码：{pagination.page}，每页：{pagination.page_size}")
    return OK(page_result, "查询成功")


@app.get("/users/{user_id}")
def get_user(user_id: int):
    """获取单个用户"""
    user = USERS.get(user_id)
    if user:
        logger.info(f"查询用户：{user_id}")
        return OK(user, "用户信息获取成功")
    
    logger.warning(f"用户不存在：{user_id}")
    return NotFound(f"用户ID {user_id} 不存在")


@app.post("/users")
def create_user(user_data: dict):
    """创建用户"""
    # 验证必填字段
    errors = []
    if not user_data.get("name"):
        errors.append("用户名不能为空")
    if not user_data.get("email"):
        errors.append("邮箱不能为空")
    
    if errors:
        return BadRequest("创建用户失败", errors)
    
    # 创建新用户
    new_id = max(USERS.keys()) + 1
    new_user = {
        "id": new_id,
        "name": user_data["name"],
        "email": user_data["email"]
    }
    USERS[new_id] = new_user
    
    logger.info(f"创建新用户：{new_user}")
    return OK(new_user, "用户创建成功")


@app.post("/auth/login")
def login(credentials: dict):
    """登录示例（演示密码验证）"""
    username = credentials.get("username")
    password = credentials.get("password")
    
    if not username or not password:
        return BadRequest("用户名和密码不能为空")
    
    # 演示密码哈希和验证
    # 实际应用中，存储的是哈希后的密码
    demo_password_hash = hash_password("demo123")
    
    if username == "demo" and verify_password(password, demo_password_hash):
        logger.info(f"用户登录成功：{username}")
        return OK(
            {
                "token": "demo-token-12345",
                "user": {"username": username}
            },
            "登录成功"
        )
    
    logger.warning(f"登录失败：{username}")
    return BadRequest("用户名或密码错误")


@app.post("/batch-import")
def batch_import(items: list):
    """批量导入示例（演示警告响应）"""
    success_count = 0
    warnings = []
    
    for idx, item in enumerate(items, start=1):
        if not item.get("name"):
            warnings.append(f"第{idx}行：名称不能为空")
        else:
            success_count += 1
    
    if warnings:
        return Warning(
            f"批量导入完成，成功 {success_count} 条，警告 {len(warnings)} 条",
            data={"success": success_count, "warnings": len(warnings)},
            msg_details=warnings
        )
    
    return OK(
        {"success": success_count},
        f"批量导入成功，共 {success_count} 条"
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting demo application...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

