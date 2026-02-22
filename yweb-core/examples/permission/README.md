# 权限模块示例

本目录包含权限模块的演示代码。

## 示例列表

| 文件 | 说明 |
|------|------|
| `demo_basic.py` | 基础用法：定义模型、创建权限角色、分配和检查权限 |
| `demo_role_inheritance.py` | 角色继承：树形角色结构、权限继承 |
| `demo_fastapi_integration.py` | FastAPI 集成：依赖注入、权限检查 |
| `demo_cache.py` | 缓存机制：缓存配置、失效策略、统计 |

## 运行示例

### 基础演示

```bash
cd examples/permission
python demo_basic.py
```

输出示例：
```
============================================================
权限模块基础演示
============================================================

--- 创建权限 ---
  创建权限: user:read - 查看用户
  创建权限: user:write - 编辑用户
  ...

--- 检查权限 ---
  employee:1 -> user:read: ✓
  employee:1 -> user:delete: ✓
  employee:2 -> user:delete: ✗
  ...
```

### 角色继承演示

```bash
python demo_role_inheritance.py
```

演示角色树：
```
super_admin (超级管理员)
└── admin (管理员)
    ├── manager (经理)
    │   └── staff (员工)
    └── auditor (审计员)
```

### FastAPI 集成演示

```bash
# 安装依赖
pip install uvicorn

# 运行
python demo_fastapi_integration.py
# 或
uvicorn demo_fastapi_integration:app --reload
```

然后访问：
- http://localhost:8000/docs - API 文档
- http://localhost:8000/users?token=token_admin - 管理员访问
- http://localhost:8000/users?token=token_user - 普通用户访问

### 缓存演示

```bash
python demo_cache.py
```

## 生成的数据库文件

运行示例会生成 SQLite 数据库文件：
- `demo_permission_basic.db`
- `demo_permission_inheritance.db`
- `demo_fastapi_permission.db`

这些文件可以删除后重新运行示例。
