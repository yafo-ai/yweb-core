# YWeb 权限模块实现计划

## 一、现有基础设施分析

### 1.1 可复用的现有模块

| 模块 | 现有功能 | 权限模块可复用点 |
|------|---------|-----------------|
| **Auth** | JWT/API Key/Session/OAuth2/OIDC 多种认证方式 | `UserIdentity` 已包含 roles/permissions 字段，可直接扩展 |
| **ORM** | BaseModel CRUD、软删除、事务管理、历史记录 | 权限相关数据模型的基类 |
| **Middleware** | 请求ID、日志、当前用户追踪 | 权限检查中间件可复用模式 |
| **Log** | 完整日志系统、敏感数据过滤 | 审计日志记录 |
| **Exceptions** | `AuthorizationException` 已存在 | 权限拒绝异常处理 |
| **Organization** | 组织/部门/员工抽象模型、TreeMixin | 部门数据隔离、内部员工集成 |

### 1.2 现有认证模块的权限相关代码

```python
# 已有的 UserIdentity 定义 (auth/base.py)
@dataclass
class UserIdentity:
    user_id: Any
    username: str
    roles: List[str] = field(default_factory=list)        # ✅ 已支持角色
    permissions: List[str] = field(default_factory=list)  # ✅ 已支持权限
    groups: List[str] = field(default_factory=list)       # ✅ 已支持用户组
    
    def has_role(self, role: str) -> bool: ...
    def has_permission(self, permission: str) -> bool: ...
```

### 1.3 现有组织模块结构

```python
# organization 模块提供的抽象模型
AbstractOrganization   # 组织
AbstractDepartment     # 部门（带 TreeMixin）
AbstractEmployee       # 员工
AbstractEmployeeOrgRel # 员工-组织关联
AbstractEmployeeDeptRel# 员工-部门关联
AbstractDepartmentLeader # 部门负责人

# 枚举
EmployeeStatus  # ACTIVE, RESIGNED, PROBATION, SUSPENDED, PENDING
ExternalSource  # NONE, WECHAT_WORK, FEISHU, DINGTALK, CUSTOM
```

---

## 二、用户体系设计

### 2.1 双用户类型支持

权限模块需要支持两种用户类型：

| 用户类型 | 说明 | 数据来源 | 典型场景 |
|---------|------|---------|---------|
| **内部员工** | 组织内的员工 | `organization.Employee` | 企业内部系统、OA |
| **外部用户** | 非组织内的用户 | `permission.ExternalUser` | 客户、合作伙伴、注册用户 |

### 2.2 统一用户抽象

```python
from enum import Enum
from typing import Union, Optional

class UserType(str, Enum):
    """用户类型"""
    EMPLOYEE = "employee"      # 内部员工
    EXTERNAL = "external"      # 外部用户

class AbstractSubject:
    """权限主体抽象基类
    
    所有可以被授权的实体（员工、外部用户）都应实现此接口
    """
    
    @property
    def subject_id(self) -> str:
        """获取主体唯一标识
        
        格式: "{user_type}:{id}"
        例如: "employee:123", "external:456"
        """
        raise NotImplementedError
    
    @property
    def subject_type(self) -> UserType:
        """获取主体类型"""
        raise NotImplementedError


class AbstractExternalUser(BaseModel):
    """外部用户抽象模型"""
    __abstract__ = True
    
    username: str          # 用户名（唯一）
    email: str             # 邮箱
    mobile: str            # 手机号
    nickname: str          # 昵称/显示名
    avatar: str            # 头像
    is_active: bool        # 是否启用
    last_login_at: datetime # 最后登录时间
    
    @property
    def subject_id(self) -> str:
        return f"external:{self.id}"
    
    @property
    def subject_type(self) -> UserType:
        return UserType.EXTERNAL
```

### 2.3 员工扩展（与 organization 集成）

```python
# 应用层实现示例
class Employee(AbstractEmployee, AbstractSubject):
    """员工模型（扩展权限主体接口）"""
    __tablename__ = "sys_employee"
    
    @property
    def subject_id(self) -> str:
        return f"employee:{self.id}"
    
    @property
    def subject_type(self) -> UserType:
        return UserType.EMPLOYEE
```

---

## 三、核心架构设计

### 3.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        权限模块架构                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    API / 装饰器 / 依赖                       │ │
│  │   @require_permission("user:read")                          │ │
│  │   Depends(PermissionChecker(permissions=["order:write"]))   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   PermissionService                          │ │
│  │   - check_permission(subject_id, permission)                 │ │
│  │   - get_user_permissions(subject_id)                         │ │
│  │   - get_user_roles(subject_id)                               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│              ┌───────────────┴───────────────┐                   │
│              ▼                               ▼                   │
│  ┌─────────────────────┐         ┌─────────────────────┐        │
│  │   PermissionCache   │         │      Database       │        │
│  │   (内存 TTL 缓存)    │◀───────▶│   (RBAC 表结构)     │        │
│  │                     │         │                     │        │
│  │  - TTLCache         │         │  - permission       │        │
│  │  - 主动失效         │         │  - role             │        │
│  │  - 版本号机制       │         │  - user_role        │        │
│  └─────────────────────┘         │  - role_permission  │        │
│                                  │  - user_permission  │        │
│                                  └─────────────────────┘        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 权限检查流程

```
请求进入
    │
    ▼
┌─────────────────┐
│ 获取用户身份     │  ← JWT/Session/API Key
│ (UserIdentity)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     命中
│ 查询权限缓存     │────────────────┐
└────────┬────────┘                │
         │ 未命中                   │
         ▼                         │
┌─────────────────┐                │
│ 查询数据库       │                │
│ - 用户直接权限   │                │
│ - 角色权限       │                │
│ - 角色继承权限   │                │
└────────┬────────┘                │
         │                         │
         ▼                         │
┌─────────────────┐                │
│ 写入缓存         │                │
└────────┬────────┘                │
         │                         │
         ▼                         ▼
┌─────────────────────────────────────┐
│           权限检查                   │
│  permission in user_permissions ?   │
└────────┬────────────────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  ✅ 通过    ❌ 拒绝
             (403)
```

---

## 四、数据模型设计

### 4.1 核心表结构

```
┌─────────────────────────────────────────────────────────────────┐
│                        RBAC 数据模型                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Employee   │     │ ExternalUser│     │    Role     │       │
│  │ (组织模块)   │     │ (权限模块)   │     │             │       │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘       │
│         │                   │                   │               │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                  SubjectRole                          │      │
│  │  subject_type | subject_id | role_id | expires_at    │      │
│  │  "employee"   | 123        | 1       | NULL          │      │
│  │  "external"   | 456        | 2       | 2026-12-31    │      │
│  └──────────────────────────────────────────────────────┘      │
│                                │                                │
│                                │                                │
│                                ▼                                │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                  RolePermission                       │      │
│  │  role_id | permission_id                              │      │
│  └──────────────────────────────────────────────────────┘      │
│                                │                                │
│                                ▼                                │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                  Permission                           │      │
│  │  id | code | name | resource | action | is_active    │      │
│  │  1  | user:read  | 查看用户 | user | read | true     │      │
│  │  2  | user:write | 编辑用户 | user | write| true     │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐      │
│  │             SubjectPermission (直接授权)              │      │
│  │  subject_type | subject_id | permission_id |expires_at│      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 抽象模型定义

```python
# ==================== 权限模型 ====================

class AbstractPermission(BaseModel):
    """权限抽象模型"""
    __abstract__ = True
    
    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False,
        comment="权限编码，如 user:read, order:write"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="权限名称"
    )
    resource: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="资源类型，如 user, order"
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="操作类型，如 read, write, delete"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=True,
        comment="权限描述"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="是否启用"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="排序"
    )


# ==================== 角色模型 ====================

class AbstractRole(BaseModel):
    """角色抽象模型（支持层级继承）"""
    __abstract__ = True
    
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False,
        comment="角色编码"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="角色名称"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=True,
        comment="角色描述"
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("role.id"), nullable=True,
        comment="父角色ID（支持继承）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="是否启用"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否系统内置（不可删除）"
    )
    # TreeMixin 字段
    path: Mapped[str] = mapped_column(
        String(500), nullable=True,
        comment="路径，如 /1/2/3/"
    )
    level: Mapped[int] = mapped_column(
        Integer, default=1,
        comment="层级"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="排序"
    )


# ==================== 主体-角色关联 ====================

class AbstractSubjectRole(BaseModel):
    """主体-角色关联（支持员工和外部用户）"""
    __abstract__ = True
    
    subject_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="主体类型: employee, external"
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="主体ID（员工ID或外部用户ID）"
    )
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role.id"), nullable=False,
        comment="角色ID"
    )
    granted_by: Mapped[int] = mapped_column(
        Integer, nullable=True,
        comment="授权人ID"
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now,
        comment="授权时间"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="过期时间（NULL 表示永不过期）"
    )
    
    # 联合唯一索引
    __table_args__ = (
        UniqueConstraint('subject_type', 'subject_id', 'role_id', name='uk_subject_role'),
    )


# ==================== 角色-权限关联 ====================

class AbstractRolePermission(BaseModel):
    """角色-权限关联"""
    __abstract__ = True
    
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role.id"), nullable=False,
        comment="角色ID"
    )
    permission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permission.id"), nullable=False,
        comment="权限ID"
    )
    
    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uk_role_permission'),
    )


# ==================== 主体直接权限 ====================

class AbstractSubjectPermission(BaseModel):
    """主体直接权限（绕过角色直接授权）"""
    __abstract__ = True
    
    subject_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="主体类型: employee, external"
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="主体ID"
    )
    permission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permission.id"), nullable=False,
        comment="权限ID"
    )
    granted_by: Mapped[int] = mapped_column(
        Integer, nullable=True,
        comment="授权人ID"
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now,
        comment="授权时间"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="过期时间"
    )
    reason: Mapped[str] = mapped_column(
        String(500), nullable=True,
        comment="授权原因"
    )
    
    __table_args__ = (
        UniqueConstraint('subject_type', 'subject_id', 'permission_id', name='uk_subject_permission'),
    )
```

---

## 五、权限缓存设计

### 5.1 缓存架构

```
┌────────────────────────────────────────────────────────────────┐
│                      权限缓存架构                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   PermissionCache                         │  │
│  │                                                           │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │  │
│  │   │ 权限缓存     │   │ 角色缓存     │   │ 角色权限    │    │  │
│  │   │ TTLCache    │   │ TTLCache    │   │ TTLCache    │    │  │
│  │   │             │   │             │   │             │    │  │
│  │   │ subject_id  │   │ subject_id  │   │ role_code   │    │  │
│  │   │    ↓        │   │    ↓        │   │    ↓        │    │  │
│  │   │ Set[perms]  │   │ Set[roles]  │   │ Set[perms]  │    │  │
│  │   └─────────────┘   └─────────────┘   └─────────────┘    │  │
│  │                                                           │  │
│  │   ┌─────────────────────────────────────────────────┐    │  │
│  │   │               失效策略                           │    │  │
│  │   │  - TTL 自动过期（默认 5 分钟）                    │    │  │
│  │   │  - 主动失效（权限变更时）                         │    │  │
│  │   │  - 版本号机制（批量失效）                         │    │  │
│  │   └─────────────────────────────────────────────────┘    │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 缓存实现

```python
from cachetools import TTLCache
from threading import Lock
from typing import Set, Optional, Dict
from dataclasses import dataclass
from datetime import datetime

@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class PermissionCache:
    """权限缓存管理器
    
    特点：
    - 基于 cachetools.TTLCache，自动过期
    - 线程安全
    - 支持主动失效
    - 版本号机制支持批量失效
    - 内置统计功能
    
    使用示例:
        cache = PermissionCache(maxsize=10000, ttl=300)
        
        # 获取用户权限
        perms = cache.get_permissions("employee:123")
        if perms is None:
            perms = load_from_db(...)
            cache.set_permissions("employee:123", perms)
        
        # 权限变更时失效
        cache.invalidate_subject("employee:123")
    """
    
    def __init__(
        self,
        maxsize: int = 10000,      # 最大缓存条目数
        ttl: int = 300,            # 过期时间（秒）
        enable_stats: bool = True  # 是否启用统计
    ):
        self._maxsize = maxsize
        self._ttl = ttl
        self._enable_stats = enable_stats
        
        # 用户权限缓存: subject_id -> Set[permission_code]
        self._permission_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 用户角色缓存: subject_id -> Set[role_code]
        self._role_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 角色权限缓存: role_code -> Set[permission_code]
        self._role_permission_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 线程锁
        self._lock = Lock()
        
        # 版本号（用于批量失效）
        self._version: int = 0
        
        # 统计
        self._stats = CacheStats() if enable_stats else None
    
    def _make_key(self, subject_id: str, prefix: str = "perm") -> str:
        """生成缓存 key"""
        return f"{prefix}:{subject_id}:v{self._version}"
    
    # ==================== 权限缓存 ====================
    
    def get_permissions(self, subject_id: str) -> Optional[Set[str]]:
        """获取用户权限"""
        key = self._make_key(subject_id, "perm")
        result = self._permission_cache.get(key)
        
        if self._stats:
            if result is not None:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
        
        return result
    
    def set_permissions(self, subject_id: str, permissions: Set[str]):
        """设置用户权限"""
        key = self._make_key(subject_id, "perm")
        with self._lock:
            self._permission_cache[key] = permissions
    
    # ==================== 角色缓存 ====================
    
    def get_roles(self, subject_id: str) -> Optional[Set[str]]:
        """获取用户角色"""
        key = self._make_key(subject_id, "role")
        return self._role_cache.get(key)
    
    def set_roles(self, subject_id: str, roles: Set[str]):
        """设置用户角色"""
        key = self._make_key(subject_id, "role")
        with self._lock:
            self._role_cache[key] = roles
    
    # ==================== 角色权限缓存 ====================
    
    def get_role_permissions(self, role_code: str) -> Optional[Set[str]]:
        """获取角色权限"""
        key = f"role_perm:{role_code}:v{self._version}"
        return self._role_permission_cache.get(key)
    
    def set_role_permissions(self, role_code: str, permissions: Set[str]):
        """设置角色权限"""
        key = f"role_perm:{role_code}:v{self._version}"
        with self._lock:
            self._role_permission_cache[key] = permissions
    
    # ==================== 失效策略 ====================
    
    def invalidate_subject(self, subject_id: str):
        """使单个主体的缓存失效"""
        with self._lock:
            perm_key = self._make_key(subject_id, "perm")
            role_key = self._make_key(subject_id, "role")
            self._permission_cache.pop(perm_key, None)
            self._role_cache.pop(role_key, None)
            
            if self._stats:
                self._stats.invalidations += 1
    
    def invalidate_role(self, role_code: str):
        """使角色权限缓存失效
        
        注意：这不会自动失效拥有该角色的用户缓存，
        需要配合 invalidate_subjects_by_role 使用
        """
        key = f"role_perm:{role_code}:v{self._version}"
        with self._lock:
            self._role_permission_cache.pop(key, None)
    
    def invalidate_subjects_batch(self, subject_ids: List[str]):
        """批量失效多个主体的缓存"""
        with self._lock:
            for subject_id in subject_ids:
                perm_key = self._make_key(subject_id, "perm")
                role_key = self._make_key(subject_id, "role")
                self._permission_cache.pop(perm_key, None)
                self._role_cache.pop(role_key, None)
            
            if self._stats:
                self._stats.invalidations += len(subject_ids)
    
    def invalidate_all(self):
        """使所有缓存失效（通过版本号递增）
        
        适用于：
        - 权限模型发生重大变更
        - 紧急清除所有缓存
        """
        with self._lock:
            self._version += 1
            # 旧版本的 key 不会命中，等待 TTL 自动清理
            
            if self._stats:
                self._stats.invalidations += 1
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._permission_cache.clear()
            self._role_cache.clear()
            self._role_permission_cache.clear()
    
    # ==================== 统计 ====================
    
    @property
    def stats(self) -> Optional[CacheStats]:
        """获取缓存统计"""
        return self._stats
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        return {
            "permission_cache_size": len(self._permission_cache),
            "role_cache_size": len(self._role_cache),
            "role_permission_cache_size": len(self._role_permission_cache),
            "maxsize": self._maxsize,
            "ttl": self._ttl,
            "version": self._version,
            "stats": {
                "hits": self._stats.hits if self._stats else 0,
                "misses": self._stats.misses if self._stats else 0,
                "hit_rate": f"{self._stats.hit_rate:.2%}" if self._stats else "N/A",
                "invalidations": self._stats.invalidations if self._stats else 0,
            }
        }


# 全局单例
permission_cache = PermissionCache()
```

### 5.3 缓存配置

```python
# config.py
class PermissionCacheSettings:
    """权限缓存配置"""
    
    # 最大缓存条目数（见下方说明）
    CACHE_MAX_SIZE: int = 10000
    
    # 缓存过期时间（秒）
    CACHE_TTL: int = 300  # 5 分钟
    
    # 是否启用缓存统计
    CACHE_ENABLE_STATS: bool = True
```

### 5.4 maxsize 参数说明

**`maxsize=10000` 是缓存条目总数，不是用户数！**

```
┌──────────────────────────────────────────────────────────────────┐
│                     缓存容量说明                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  permission_cache (用户权限)                                │  │
│  │  maxsize = 10000                                           │  │
│  │  key: "perm:employee:123:v1"  →  value: {"user:read", ...} │  │
│  │                                                            │  │
│  │  实际含义：最多缓存 10000 个用户的权限集合                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  role_cache (用户角色)                                      │  │
│  │  maxsize = 10000                                           │  │
│  │  key: "role:employee:123:v1"  →  value: {"admin", ...}     │  │
│  │                                                            │  │
│  │  实际含义：最多缓存 10000 个用户的角色集合                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  role_permission_cache (角色权限)                           │  │
│  │  maxsize = 10000                                           │  │
│  │  key: "role_perm:admin:v1"  →  value: {"user:read", ...}   │  │
│  │                                                            │  │
│  │  实际含义：最多缓存 10000 个角色的权限集合                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  总结：                                                          │
│  - 3 个独立的 TTLCache，每个 maxsize=10000                       │
│  - 支持 ~10000 个活跃用户 + ~10000 个角色的缓存                  │
│  - 超出 maxsize 时，LRU 策略自动淘汰最久未使用的条目              │
│  - 根据实际用户量调整，建议 maxsize = 活跃用户数 * 1.5           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**容量规划建议：**

| 活跃用户数 | 建议 maxsize | 预估内存占用 |
|-----------|-------------|-------------|
| 1,000 | 2,000 | ~10 MB |
| 10,000 | 15,000 | ~100 MB |
| 100,000 | 150,000 | ~1 GB |

### 5.5 权限变更自动刷新缓存

**设计原则：所有权限变更操作都会自动触发缓存失效**

```
┌────────────────────────────────────────────────────────────────┐
│                   缓存自动刷新机制                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  权限变更场景                        自动触发的缓存操作         │
│  ─────────────────────────────────   ─────────────────────────  │
│                                                                │
│  1. 给用户分配角色                                              │
│     assign_role_to_subject()                                   │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_subject(subject_id)  ← 失效该用户缓存     │
│                                                                │
│  2. 移除用户角色                                                │
│     revoke_role_from_subject()                                 │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_subject(subject_id)  ← 失效该用户缓存     │
│                                                                │
│  3. 给用户直接授权                                              │
│     grant_permission_to_subject()                              │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_subject(subject_id)  ← 失效该用户缓存     │
│                                                                │
│  4. 修改角色权限                                                │
│     update_role_permissions()                                  │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_role(role_code)      ← 失效角色权限缓存   │
│                 │                                              │
│                 ▼                                              │
│     for user in users_with_role:          ← 失效所有相关用户   │
│         cache.invalidate_subject(user.subject_id)              │
│                                                                │
│  5. 删除/禁用角色                                               │
│     delete_role() / disable_role()                             │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_role(role_code)                           │
│     cache.invalidate_subjects_batch(affected_users)            │
│                                                                │
│  6. 删除/禁用权限                                               │
│     delete_permission() / disable_permission()                 │
│                 │                                              │
│                 ▼                                              │
│     cache.invalidate_all()                ← 全量失效（版本号+1）│
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**代码实现示例：**

```python
class PermissionService:
    """所有变更方法都内置缓存失效逻辑"""
    
    def assign_role_to_subject(self, subject_id: str, role_code: str, **kwargs):
        """给主体分配角色"""
        # 1. 数据库操作
        subject_type, sid = subject_id.split(":", 1)
        role = Role.query.filter_by(code=role_code).first()
        sr = SubjectRole(
            subject_type=subject_type,
            subject_id=int(sid),
            role_id=role.id,
            **kwargs
        )
        sr.save(commit=True)
        
        # 2. ✅ 自动失效缓存（用户下次请求会重新加载）
        self._cache.invalidate_subject(subject_id)
    
    def update_role_permissions(self, role_code: str, permission_codes: List[str]):
        """更新角色权限"""
        role = Role.query.filter_by(code=role_code).first()
        
        # 1. 数据库操作
        RolePermission.query.filter_by(role_id=role.id).delete()
        for code in permission_codes:
            perm = Permission.query.filter_by(code=code).first()
            if perm:
                RolePermission(role_id=role.id, permission_id=perm.id).save()
        
        # 2. ✅ 失效角色权限缓存
        self._cache.invalidate_role(role_code)
        
        # 3. ✅ 失效所有拥有该角色的用户缓存
        affected_subjects = SubjectRole.query.filter_by(role_id=role.id).all()
        subject_ids = [f"{sr.subject_type}:{sr.subject_id}" for sr in affected_subjects]
        self._cache.invalidate_subjects_batch(subject_ids)
```

**注意事项：**

1. **通过 PermissionService 操作** - 只要通过服务层方法操作，缓存会自动刷新
2. **直接操作数据库** - 如果直接操作 ORM 模型，需要手动调用 `cache.invalidate_xxx()`
3. **批量操作优化** - 批量变更时使用 `invalidate_subjects_batch()` 减少开销

---

## 六、WebAPI 级别权限管理

### 6.1 API 资源模型

为了支持其他项目通过 WebAPI 进行权限管理，需要设计 **API 资源模型**：

```
┌────────────────────────────────────────────────────────────────────┐
│                    WebAPI 权限管理架构                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                   API 资源表 (api_resource)                   │  │
│  │                                                              │  │
│  │  id | path            | method | name     | permission_code  │  │
│  │  ───┼─────────────────┼────────┼──────────┼─────────────────  │  │
│  │  1  | /api/users      | GET    | 用户列表  | user:list        │  │
│  │  2  | /api/users      | POST   | 创建用户  | user:create      │  │
│  │  3  | /api/users/{id} | GET    | 用户详情  | user:read        │  │
│  │  4  | /api/users/{id} | PUT    | 修改用户  | user:update      │  │
│  │  5  | /api/users/{id} | DELETE | 删除用户  | user:delete      │  │
│  │  6  | /api/orders     | GET    | 订单列表  | order:list       │  │
│  │  ...                                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                     │
│                              │ 关联                                 │
│                              ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                   权限表 (permission)                         │  │
│  │                                                              │  │
│  │  id | code        | name     | resource | action             │  │
│  │  ───┼─────────────┼──────────┼──────────┼───────             │  │
│  │  1  | user:list   | 用户列表 | user     | list               │  │
│  │  2  | user:create | 创建用户 | user     | create             │  │
│  │  ...                                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 6.2 API 资源抽象模型

```python
class AbstractAPIResource(BaseModel):
    """API 资源抽象模型
    
    将 HTTP 路由与权限关联，支持：
    1. 自动扫描 FastAPI 路由并生成资源
    2. 手动配置 API 与权限的映射
    3. 中间件自动检查 API 权限
    """
    __abstract__ = True
    
    path: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="API 路径，如 /api/users/{id}"
    )
    method: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="HTTP 方法: GET, POST, PUT, DELETE"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="API 名称/描述"
    )
    permission_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("permission.id"), nullable=True,
        comment="关联的权限ID（NULL 表示公开访问）"
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否公开访问（无需权限）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="是否启用"
    )
    module: Mapped[str] = mapped_column(
        String(50), nullable=True,
        comment="所属模块，用于分组管理"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="排序"
    )
    
    __table_args__ = (
        UniqueConstraint('path', 'method', name='uk_api_resource'),
    )
```

### 6.3 API 权限检查中间件

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class APIPermissionMiddleware(BaseHTTPMiddleware):
    """API 权限检查中间件
    
    自动检查请求的 API 是否有权限访问
    
    工作流程：
    1. 从请求中获取当前用户
    2. 根据请求路径和方法查找 API 资源配置
    3. 检查用户是否有对应权限
    4. 无权限则返回 403
    """
    
    def __init__(self, app, permission_service: PermissionService):
        super().__init__(app)
        self.permission_service = permission_service
        self._api_cache = {}  # path+method -> permission_code
    
    async def dispatch(self, request: Request, call_next):
        # 1. 获取当前用户
        user = getattr(request.state, 'user', None)
        if not user:
            return await call_next(request)  # 未登录，交给后续处理
        
        # 2. 查找 API 资源配置
        api_resource = self._get_api_resource(request.url.path, request.method)
        
        if not api_resource:
            return await call_next(request)  # 未配置，默认放行
        
        if api_resource.is_public:
            return await call_next(request)  # 公开 API，放行
        
        # 3. 检查权限
        if api_resource.permission_id:
            subject_id = f"{user.user_type}:{user.user_id}"
            permission_code = api_resource.permission.code
            
            if not self.permission_service.check_permission(subject_id, permission_code):
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": 403,
                        "message": f"无权限访问: {permission_code}",
                        "data": None
                    }
                )
        
        return await call_next(request)
    
    def _get_api_resource(self, path: str, method: str):
        """查找匹配的 API 资源（支持路径参数匹配）"""
        # 实现路径匹配逻辑，如 /api/users/123 匹配 /api/users/{id}
        ...
```

### 6.4 权限管理 WebAPI

提供完整的 RESTful API 供其他项目调用：

```python
# yweb/permission/api/routes.py

from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/permissions", tags=["权限管理"])

# ==================== 权限管理 ====================

@router.get("/permissions", summary="获取权限列表")
async def list_permissions(
    resource: Optional[str] = Query(None, description="按资源筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取权限列表（分页）"""
    ...

@router.post("/permissions", summary="创建权限")
async def create_permission(data: PermissionCreate):
    """创建新权限"""
    ...

@router.put("/permissions/{permission_id}", summary="更新权限")
async def update_permission(permission_id: int, data: PermissionUpdate):
    """更新权限"""
    ...

@router.delete("/permissions/{permission_id}", summary="删除权限")
async def delete_permission(permission_id: int):
    """删除权限"""
    ...

# ==================== 角色管理 ====================

@router.get("/roles", summary="获取角色列表")
async def list_roles():
    """获取所有角色（树形结构）"""
    ...

@router.post("/roles", summary="创建角色")
async def create_role(data: RoleCreate):
    """创建新角色"""
    ...

@router.put("/roles/{role_id}", summary="更新角色")
async def update_role(role_id: int, data: RoleUpdate):
    """更新角色基本信息"""
    ...

@router.delete("/roles/{role_id}", summary="删除角色")
async def delete_role(role_id: int):
    """删除角色"""
    ...

@router.get("/roles/{role_id}/permissions", summary="获取角色权限")
async def get_role_permissions(role_id: int):
    """获取角色的所有权限"""
    ...

@router.put("/roles/{role_id}/permissions", summary="设置角色权限")
async def set_role_permissions(role_id: int, permission_ids: List[int]):
    """设置角色的权限（全量覆盖）"""
    ...

# ==================== 用户权限管理 ====================

@router.get("/subjects/{subject_id}/roles", summary="获取用户角色")
async def get_subject_roles(subject_id: str):
    """获取用户的所有角色
    
    Args:
        subject_id: 用户标识，如 employee:123 或 external:456
    """
    ...

@router.post("/subjects/{subject_id}/roles", summary="分配用户角色")
async def assign_subject_role(
    subject_id: str,
    data: AssignRoleRequest
):
    """给用户分配角色
    
    支持设置过期时间（临时角色）
    """
    ...

@router.delete("/subjects/{subject_id}/roles/{role_code}", summary="移除用户角色")
async def revoke_subject_role(subject_id: str, role_code: str):
    """移除用户的角色"""
    ...

@router.get("/subjects/{subject_id}/permissions", summary="获取用户权限")
async def get_subject_permissions(subject_id: str):
    """获取用户的所有权限（包含角色继承的）"""
    ...

@router.post("/subjects/{subject_id}/permissions", summary="直接授予权限")
async def grant_subject_permission(
    subject_id: str,
    data: GrantPermissionRequest
):
    """直接给用户授予权限（绕过角色）
    
    支持设置过期时间（临时权限）
    """
    ...

# ==================== API 资源管理 ====================

@router.get("/api-resources", summary="获取 API 资源列表")
async def list_api_resources(
    module: Optional[str] = Query(None, description="按模块筛选"),
):
    """获取所有 API 资源配置"""
    ...

@router.post("/api-resources", summary="创建 API 资源")
async def create_api_resource(data: APIResourceCreate):
    """手动创建 API 资源配置"""
    ...

@router.put("/api-resources/{resource_id}", summary="更新 API 资源")
async def update_api_resource(resource_id: int, data: APIResourceUpdate):
    """更新 API 资源配置（如关联权限）"""
    ...

@router.post("/api-resources/scan", summary="扫描 FastAPI 路由")
async def scan_api_routes():
    """自动扫描 FastAPI 应用的所有路由，生成 API 资源配置建议"""
    ...

# ==================== 权限检查 ====================

@router.post("/check", summary="检查权限")
async def check_permission(
    subject_id: str,
    permission_code: str
):
    """检查用户是否有某个权限
    
    返回: { "has_permission": true/false }
    """
    ...

@router.post("/check-batch", summary="批量检查权限")
async def check_permissions_batch(
    subject_id: str,
    permission_codes: List[str]
):
    """批量检查用户的多个权限
    
    返回: { "user:read": true, "user:write": false, ... }
    """
    ...

# ==================== 缓存管理 ====================

@router.get("/cache/stats", summary="获取缓存统计")
async def get_cache_stats():
    """获取权限缓存统计信息"""
    return permission_cache.get_cache_info()

@router.post("/cache/invalidate/{subject_id}", summary="失效用户缓存")
async def invalidate_subject_cache(subject_id: str):
    """手动失效指定用户的权限缓存"""
    permission_cache.invalidate_subject(subject_id)
    return {"message": f"已失效用户 {subject_id} 的缓存"}

@router.post("/cache/invalidate-all", summary="失效所有缓存")
async def invalidate_all_cache():
    """失效所有权限缓存（谨慎使用）"""
    permission_cache.invalidate_all()
    return {"message": "已失效所有缓存"}
```

### 6.5 在其他项目中使用

```python
# 其他项目的 main.py

from fastapi import FastAPI
from yweb.permission import (
    permission_router,           # 权限管理 API
    APIPermissionMiddleware,     # API 权限检查中间件
    PermissionService,
)

app = FastAPI()

# 1. 注册权限管理 API
app.include_router(permission_router, prefix="/api")

# 2. 添加 API 权限检查中间件（可选）
app.add_middleware(
    APIPermissionMiddleware,
    permission_service=PermissionService()
)

# 3. 通过 HTTP 调用管理权限
# POST /api/permissions/roles
# PUT /api/permissions/roles/1/permissions
# POST /api/permissions/subjects/employee:123/roles
# GET /api/permissions/check?subject_id=employee:123&permission_code=user:read
```

### 6.6 API 权限配置示例

```python
# 方式1: 通过 API 配置
import httpx

# 创建权限
httpx.post("/api/permissions/permissions", json={
    "code": "order:approve",
    "name": "审批订单",
    "resource": "order",
    "action": "approve"
})

# 创建 API 资源并关联权限
httpx.post("/api/permissions/api-resources", json={
    "path": "/api/orders/{id}/approve",
    "method": "POST",
    "name": "审批订单",
    "permission_code": "order:approve",  # 关联权限
    "module": "order"
})

# 给用户分配角色
httpx.post("/api/permissions/subjects/employee:123/roles", json={
    "role_code": "order_manager",
    "expires_at": "2026-12-31T23:59:59"  # 可选，临时角色
})

# 检查权限
response = httpx.post("/api/permissions/check", json={
    "subject_id": "employee:123",
    "permission_code": "order:approve"
})
print(response.json())  # {"has_permission": true}
```

---

## 七、分阶段实现计划

### 阶段一：核心 RBAC 框架 + 缓存（第1-2周）

**目标：建立基础权限模型、缓存机制和检查器**

#### 7.1.1 模块目录结构

```
yweb/
├── permission/
│   ├── __init__.py              # 模块入口
│   │
│   ├── models/                  # 抽象数据模型
│   │   ├── __init__.py
│   │   ├── permission.py        # AbstractPermission
│   │   ├── role.py              # AbstractRole
│   │   ├── external_user.py     # AbstractExternalUser
│   │   ├── subject_role.py      # AbstractSubjectRole
│   │   ├── role_permission.py   # AbstractRolePermission
│   │   └── subject_permission.py# AbstractSubjectPermission
│   │
│   ├── schemas/                 # Pydantic Schema
│   │   ├── __init__.py
│   │   ├── permission_schemas.py
│   │   ├── role_schemas.py
│   │   └── user_schemas.py
│   │
│   ├── services/                # 业务服务
│   │   ├── __init__.py
│   │   ├── permission_service.py
│   │   └── role_service.py
│   │
│   ├── cache.py                 # 权限缓存
│   ├── dependencies.py          # FastAPI 依赖
│   ├── decorators.py            # 装饰器
│   ├── enums.py                 # 枚举定义
│   ├── exceptions.py            # 异常定义
│   └── types.py                 # 类型定义
```

#### 7.1.2 权限服务实现

```python
class PermissionService:
    """权限服务
    
    提供权限检查、查询、管理等功能，内置缓存支持。
    
    使用示例:
        service = PermissionService()
        
        # 检查权限
        has_perm = service.check_permission("employee:123", "user:read")
        
        # 获取用户所有权限
        perms = service.get_subject_permissions("employee:123")
    """
    
    def __init__(self, cache: PermissionCache = None):
        self._cache = cache or permission_cache
    
    def check_permission(
        self,
        subject_id: str,
        permission_code: str
    ) -> bool:
        """检查主体是否拥有指定权限
        
        Args:
            subject_id: 主体标识，如 "employee:123"
            permission_code: 权限编码，如 "user:read"
        
        Returns:
            是否拥有权限
        """
        permissions = self.get_subject_permissions(subject_id)
        return permission_code in permissions
    
    def check_any_permission(
        self,
        subject_id: str,
        permission_codes: List[str]
    ) -> bool:
        """检查主体是否拥有任一权限"""
        permissions = self.get_subject_permissions(subject_id)
        return any(code in permissions for code in permission_codes)
    
    def check_all_permissions(
        self,
        subject_id: str,
        permission_codes: List[str]
    ) -> bool:
        """检查主体是否拥有所有权限"""
        permissions = self.get_subject_permissions(subject_id)
        return all(code in permissions for code in permission_codes)
    
    def get_subject_permissions(self, subject_id: str) -> Set[str]:
        """获取主体的所有权限（缓存优先）
        
        包括：
        1. 直接授予的权限
        2. 通过角色获得的权限
        3. 通过角色继承获得的权限
        """
        # 1. 查缓存
        cached = self._cache.get_permissions(subject_id)
        if cached is not None:
            return cached
        
        # 2. 从数据库加载
        permissions = self._load_permissions_from_db(subject_id)
        
        # 3. 写入缓存
        self._cache.set_permissions(subject_id, permissions)
        
        return permissions
    
    def _load_permissions_from_db(self, subject_id: str) -> Set[str]:
        """从数据库加载权限"""
        subject_type, sid = subject_id.split(":", 1)
        sid = int(sid)
        permissions = set()
        now = datetime.now()
        
        # 1. 直接权限（未过期的）
        direct_perms = SubjectPermission.query.filter(
            SubjectPermission.subject_type == subject_type,
            SubjectPermission.subject_id == sid,
            (SubjectPermission.expires_at.is_(None) | (SubjectPermission.expires_at > now))
        ).all()
        
        for sp in direct_perms:
            if sp.permission.is_active:
                permissions.add(sp.permission.code)
        
        # 2. 角色权限
        subject_roles = SubjectRole.query.filter(
            SubjectRole.subject_type == subject_type,
            SubjectRole.subject_id == sid,
            (SubjectRole.expires_at.is_(None) | (SubjectRole.expires_at > now))
        ).all()
        
        for sr in subject_roles:
            if sr.role.is_active:
                # 获取角色权限（包含继承）
                role_perms = self._get_role_permissions_with_inheritance(sr.role)
                permissions.update(role_perms)
        
        return permissions
    
    def _get_role_permissions_with_inheritance(self, role) -> Set[str]:
        """获取角色权限（包含父角色继承的权限）"""
        # 查缓存
        cached = self._cache.get_role_permissions(role.code)
        if cached is not None:
            return cached
        
        permissions = set()
        
        # 当前角色的权限
        for rp in role.permissions:
            if rp.permission.is_active:
                permissions.add(rp.permission.code)
        
        # 递归获取父角色的权限
        if role.parent_id:
            parent = Role.get(role.parent_id)
            if parent and parent.is_active:
                parent_perms = self._get_role_permissions_with_inheritance(parent)
                permissions.update(parent_perms)
        
        # 写入缓存
        self._cache.set_role_permissions(role.code, permissions)
        
        return permissions
    
    # ==================== 权限管理 ====================
    
    def assign_role_to_subject(
        self,
        subject_id: str,
        role_code: str,
        granted_by: int = None,
        expires_at: datetime = None
    ):
        """给主体分配角色"""
        subject_type, sid = subject_id.split(":", 1)
        role = Role.query.filter_by(code=role_code).first()
        
        if not role:
            raise ValueError(f"角色不存在: {role_code}")
        
        sr = SubjectRole(
            subject_type=subject_type,
            subject_id=int(sid),
            role_id=role.id,
            granted_by=granted_by,
            expires_at=expires_at
        )
        sr.save(commit=True)
        
        # 失效缓存
        self._cache.invalidate_subject(subject_id)
    
    def revoke_role_from_subject(self, subject_id: str, role_code: str):
        """移除主体的角色"""
        subject_type, sid = subject_id.split(":", 1)
        role = Role.query.filter_by(code=role_code).first()
        
        if role:
            SubjectRole.query.filter_by(
                subject_type=subject_type,
                subject_id=int(sid),
                role_id=role.id
            ).delete()
        
        # 失效缓存
        self._cache.invalidate_subject(subject_id)
    
    def update_role_permissions(self, role_code: str, permission_codes: List[str]):
        """更新角色的权限"""
        role = Role.query.filter_by(code=role_code).first()
        if not role:
            raise ValueError(f"角色不存在: {role_code}")
        
        # 删除旧权限
        RolePermission.query.filter_by(role_id=role.id).delete()
        
        # 添加新权限
        for code in permission_codes:
            perm = Permission.query.filter_by(code=code).first()
            if perm:
                RolePermission(role_id=role.id, permission_id=perm.id).save()
        
        # 失效相关缓存
        self._cache.invalidate_role(role_code)
        self._invalidate_subjects_with_role(role_code)
    
    def _invalidate_subjects_with_role(self, role_code: str):
        """失效拥有指定角色的所有主体的缓存"""
        role = Role.query.filter_by(code=role_code).first()
        if not role:
            return
        
        subject_roles = SubjectRole.query.filter_by(role_id=role.id).all()
        subject_ids = [f"{sr.subject_type}:{sr.subject_id}" for sr in subject_roles]
        
        self._cache.invalidate_subjects_batch(subject_ids)
```

#### 7.1.3 交付物

- [ ] 抽象数据模型（权限、角色、关联表、外部用户）
- [ ] 权限缓存实现（TTLCache + 失效策略）
- [ ] 权限服务类（检查 + 管理）
- [ ] FastAPI 依赖注入集成
- [ ] 权限检查装饰器
- [ ] 与 `UserIdentity` 的集成
- [ ] 与 `organization.Employee` 的集成
- [ ] 单元测试

---

### 阶段二：高级功能（第3-4周）

**目标：角色继承、临时权限、权限管理 API**

#### 7.2.1 角色继承（使用 TreeMixin）

```python
from yweb.organization import TreeMixin

class AbstractRole(BaseModel, TreeMixin):
    """角色模型（支持树形继承）"""
    __abstract__ = True
    
    # ... 字段定义 ...
    
    def get_all_permissions(self) -> Set[str]:
        """获取角色及其所有父角色的权限"""
        permissions = set()
        
        # 当前角色权限
        for rp in self.permissions:
            permissions.add(rp.permission.code)
        
        # 父角色权限（递归）
        for ancestor in self.get_ancestors():
            for rp in ancestor.permissions:
                permissions.add(rp.permission.code)
        
        return permissions
```

#### 7.2.2 临时权限清理任务

```python
from datetime import datetime

class PermissionCleanupService:
    """权限清理服务"""
    
    @staticmethod
    def cleanup_expired():
        """清理过期的权限和角色分配
        
        建议通过定时任务定期执行
        """
        now = datetime.now()
        
        # 清理过期的主体-角色关联
        expired_roles = SubjectRole.query.filter(
            SubjectRole.expires_at.isnot(None),
            SubjectRole.expires_at < now
        ).all()
        
        for sr in expired_roles:
            subject_id = f"{sr.subject_type}:{sr.subject_id}"
            sr.delete()
            permission_cache.invalidate_subject(subject_id)
        
        # 清理过期的直接权限
        expired_perms = SubjectPermission.query.filter(
            SubjectPermission.expires_at.isnot(None),
            SubjectPermission.expires_at < now
        ).all()
        
        for sp in expired_perms:
            subject_id = f"{sp.subject_type}:{sp.subject_id}"
            sp.delete()
            permission_cache.invalidate_subject(subject_id)
        
        return {
            "expired_roles": len(expired_roles),
            "expired_permissions": len(expired_perms)
        }
```

#### 7.2.3 交付物

- [ ] 角色继承实现（TreeMixin）
- [ ] 临时权限支持（带过期时间）
- [ ] 过期权限清理服务
- [ ] 权限管理 API Router

---

### 阶段三：数据级权限（第5-6周）

**目标：实现行级数据权限控制**

#### 7.3.1 数据权限策略模型

```python
class DataScopeType(str, Enum):
    """数据范围类型"""
    ALL = "all"              # 全部数据
    SELF = "self"            # 仅本人数据
    DEPT = "dept"            # 本部门数据
    DEPT_AND_CHILDREN = "dept_and_children"  # 本部门及下级
    CUSTOM = "custom"        # 自定义

class AbstractDataPermissionPolicy(BaseModel):
    """数据权限策略"""
    __abstract__ = True
    
    name: str                    # 策略名称
    resource: str                # 资源（表名/模型名）
    scope_type: str              # 数据范围类型
    custom_condition: str        # 自定义条件（scope_type=custom 时使用）
    description: str
    is_active: bool
```

#### 7.3.2 数据权限过滤器

```python
class DataPermissionFilter:
    """数据权限过滤器
    
    根据用户的数据权限策略，自动过滤查询结果
    """
    
    def apply(
        self,
        query,
        user: UserIdentity,
        resource: str
    ):
        """应用数据权限过滤
        
        Args:
            query: SQLAlchemy 查询对象
            user: 当前用户
            resource: 资源名称
        
        Returns:
            过滤后的查询对象
        """
        policy = self._get_policy(user, resource)
        
        if policy.scope_type == DataScopeType.ALL:
            return query
        
        if policy.scope_type == DataScopeType.SELF:
            return query.filter(Model.created_by == user.user_id)
        
        if policy.scope_type == DataScopeType.DEPT:
            return query.filter(Model.dept_id == user.dept_id)
        
        if policy.scope_type == DataScopeType.DEPT_AND_CHILDREN:
            dept_ids = self._get_dept_and_children_ids(user.dept_id)
            return query.filter(Model.dept_id.in_(dept_ids))
        
        # custom: 使用自定义条件
        return query
```

#### 7.3.3 交付物

- [ ] 数据权限策略模型
- [ ] 数据权限过滤器
- [ ] 与 ORM 查询的集成
- [ ] 部门数据隔离实现（与 organization 集成）

---

### 关于审计日志

**不需要单独实现！** 复用现有的 `yweb.orm.history` 模块：

```python
# 权限模型启用 history，自动记录所有变更
class Permission(AbstractPermission):
    enable_history = True
    __tablename__ = "permission"

class Role(AbstractRole):
    enable_history = True
    __tablename__ = "role"

class SubjectRole(AbstractSubjectRole):
    enable_history = True
    __tablename__ = "subject_role"
```

**history 模块已提供的功能：**
- ✅ 自动记录模型变更历史
- ✅ 当前用户追踪（CurrentUserPlugin）
- ✅ 版本差异比较（get_history_diff）
- ✅ 版本恢复（restore_to_version）

**权限拒绝日志** 使用现有的 `log` 模块：

```python
from yweb.log import auth_logger

# 权限检查失败时
auth_logger.warning(f"权限拒绝: subject={subject_id}, permission={permission_code}")
```

---

## 八、使用示例

### 8.1 基础权限检查

```python
from fastapi import FastAPI, Depends
from yweb.permission import (
    require_permission,
    require_roles,
    PermissionChecker,
    get_current_user_with_permissions
)

app = FastAPI()

# 方式1: 装饰器
@app.post("/users")
@require_permission("user:create")
async def create_user(data: UserCreate):
    ...

# 方式2: 依赖注入
@app.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    user = Depends(get_current_user_with_permissions),
    _check = Depends(PermissionChecker(permissions=["order:read"]))
):
    ...

# 方式3: 在函数内检查
@app.put("/users/{user_id}")
async def update_user(
    user_id: int,
    perm_service: PermissionService = Depends(),
    user = Depends(get_current_user_with_permissions)
):
    subject_id = f"{user.user_type}:{user.user_id}"
    if not perm_service.check_permission(subject_id, "user:update"):
        raise PermissionDeniedException("无权修改用户")
    ...
```

### 8.2 支持内部员工和外部用户

```python
# 内部员工
employee_subject_id = f"employee:{employee.id}"  # "employee:123"
perm_service.check_permission(employee_subject_id, "order:approve")

# 外部用户
external_subject_id = f"external:{external_user.id}"  # "external:456"
perm_service.check_permission(external_subject_id, "order:view")

# 给内部员工分配角色
perm_service.assign_role_to_subject(
    "employee:123",
    "order_manager",
    expires_at=None  # 永久
)

# 给外部用户分配临时权限
perm_service.assign_direct_permission(
    "external:456",
    "report:view",
    expires_at=datetime(2026, 12, 31)  # 2026年底过期
)
```

### 8.3 查看缓存状态

```python
from yweb.permission import permission_cache

# 获取缓存信息
info = permission_cache.get_cache_info()
print(info)
# {
#     "permission_cache_size": 1234,
#     "role_cache_size": 567,
#     "maxsize": 10000,
#     "ttl": 300,
#     "stats": {
#         "hits": 45678,
#         "misses": 1234,
#         "hit_rate": "97.36%",
#         "invalidations": 89
#     }
# }
```

---

## 九、技术依赖

### 9.1 必需依赖

```txt
# requirements.txt 新增
cachetools>=5.3.0
```

### 9.2 可选依赖

```txt
# 如需 Redis 缓存（多实例部署）
redis>=4.0.0
```

---

## 十、时间线总结

| 阶段 | 内容 | 时间 | 里程碑 |
|------|------|------|--------|
| 阶段一 | RBAC 框架 + 内存缓存 + WebAPI | 第1-2周 | ✅ 基础权限检查可用 |
| 阶段二 | 高级功能（继承、临时权限） | 第3-4周 | ✅ 角色继承、权限管理 API |
| 阶段三 | 数据级权限 | 第5-6周 | ✅ 行级数据过滤可用 |

**总预估工时：6周（1人全职）**

> 注：审计功能复用 `yweb.orm.history` 模块，无需单独开发

---

## 十一、后期扩展（可选）

### 11.1 Redis 缓存支持

如果需要多实例部署，可以添加 Redis 缓存支持：

```python
class HybridPermissionCache:
    """混合缓存：本地 + Redis"""
    
    def __init__(self, redis_client=None):
        self._local = PermissionCache(maxsize=5000, ttl=60)
        self._redis = RedisPermissionCache(redis_client) if redis_client else None
```

### 11.2 字段级权限

根据需要，可以扩展字段级权限控制。

### 11.3 可视化管理界面

前端管理界面开发。

---

*文档版本: 2.0*  
*创建时间: 2026-01-18*  
*最后更新: 2026-01-18*  
*变更说明: 移除 Casbin，采用自研 RBAC + 内存缓存方案；添加双用户类型支持（内部员工、外部用户）*
