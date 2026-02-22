# JWT Token 认证与刷新机制规范

本文档定义了基于 yweb 框架的 JWT Token 认证和自动刷新机制的前后端开发规范。

---

## 目录

1. [认证机制概述](#1-认证机制概述)
2. [后端 API 认证规范](#2-后端-api-认证规范)
3. [前端 Token 刷新机制](#3-前端-token-刷新机制)
4. [配置说明](#4-配置说明)
5. [完整示例](#5-完整示例)
6. [常见问题排查](#6-常见问题排查)
7. [最佳实践总结](#7-最佳实践总结)

---

## 1. 认证机制概述

### 1.1 双 Token 机制

系统采用 Access Token + Refresh Token 的双 Token 机制：

| Token 类型 | 有效期 | 用途 |
|-----------|--------|------|
| Access Token | 30 分钟（可配置） | 用于 API 请求认证 |
| Refresh Token | 7 天（可配置） | 用于刷新 Access Token |

### 1.2 认证流程

```
┌─────────┐                    ┌─────────┐                    ┌─────────┐
│  前端   │                    │  后端   │                    │   DB    │
└────┬────┘                    └────┬────┘                    └────┬────┘
     │                              │                              │
     │  1. 登录请求 (username/password)                            │
     │─────────────────────────────>│                              │
     │                              │  验证用户                     │
     │                              │─────────────────────────────>│
     │                              │<─────────────────────────────│
     │  2. 返回 access_token + refresh_token                       │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  3. API 请求 (Authorization: Bearer access_token)           │
     │─────────────────────────────>│                              │
     │  4. 返回数据                  │                              │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  5. access_token 过期后请求   │                              │
     │─────────────────────────────>│                              │
     │  6. 返回 401 Unauthorized     │                              │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  7. 使用 refresh_token 刷新   │                              │
     │─────────────────────────────>│                              │
     │  8. 返回新的 access_token     │                              │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  9. 使用新 token 重试原请求   │                              │
     │─────────────────────────────>│                              │
     │  10. 返回数据                 │                              │
     │<─────────────────────────────│                              │
```

---

## 2. 后端 API 认证规范

### 2.1 路由级别认证（推荐）

**在 APIRouter 级别添加认证依赖**，该路由器下所有接口自动需要认证：

```python
from fastapi import APIRouter, Depends
from app.api.dependencies import auth

# ✅ 推荐：路由级别认证
router = APIRouter(
    prefix="/org",
    tags=["组织架构"],
    dependencies=[Depends(auth.get_current_user)]  # 所有接口需要认证
)

@router.get("/list")
def org_list():  # 不需要在参数中写 Depends
    """获取组织列表"""
    ...

@router.post("/create")
def org_create(req: OrgCreateRequest):  # 不需要在参数中写 Depends
    """创建组织"""
    ...
```

### 2.2 函数级别认证（不推荐）

如果需要更细粒度的控制，可以在函数参数中添加：

```python
# ❌ 不推荐：每个函数都要写
@router.get("/list")
def org_list(_=Depends(auth.get_current_user)):
    ...

@router.post("/create")
def org_create(req: OrgCreateRequest, _=Depends(auth.get_current_user)):
    ...
```

### 2.3 公开接口（无需认证）

对于不需要认证的接口（如登录、注册），使用单独的路由器：

```python
# 公开路由器（不需要认证）
public_router = APIRouter(prefix="/auth", tags=["认证"])

@public_router.post("/login")
def login(request: LoginRequest):
    """用户登录 - 无需认证"""
    ...

@public_router.post("/refresh")
def refresh_token(refresh_token: str):
    """刷新 Token - 无需认证"""
    ...
```

### 2.4 认证依赖定义

**推荐方式：setup_auth 一站式设置**

```python
# app/api/dependencies.py

from yweb.auth import setup_auth
from app.domain.auth.model.user import User  # 继承自 AbstractUser 的项目用户模型
from app.config import settings

# 一站式认证设置（自动处理 JWT 管理器、用户缓存、缓存失效）
auth = setup_auth(User, jwt_settings=settings.jwt, token_url="/api/v1/auth/token")

# 使用: Depends(auth.get_current_user), auth.jwt_manager, auth.user_getter 等
```

> User 模型推荐继承 `yweb.auth.AbstractUser`，详见 [认证指南 - 一站式认证设置](../06_auth_guide.md#一站式认证设置-setup_auth推荐)。

<details>
<summary>手动方式（需要完全自定义时）</summary>

```python
# app/api/dependencies.py

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from app.services.jwt_service import jwt_manager, verify_token
from app.domain.auth.model.user import User
from yweb.auth import create_auth_dependency

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_user_by_id(user_id: int):
    """通过用户 ID 获取用户"""
    user = User.get_by_id(user_id)
    if user and user.is_active:
        return user
    return None

# 使用 yweb.auth 创建认证依赖
get_current_user = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=True,  # 验证失败时抛出 HTTPException
)
```
</details>

### 2.5 刷新 Token API

框架通过 `setup_auth(auth_routes=True)` 自动挂载 `/api/v1/auth/refresh` 端点，无需手动编写。

**请求格式**（request body）：

```json
POST /api/v1/auth/refresh
Content-Type: application/json

{"refresh_token": "eyJhbGciOiJIUzI1NiIs..."}
```

**成功响应**（BaseResponse）：

```json
{
    "status": "success",
    "message": "刷新令牌成功",
    "msg_details": [],
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer"
    }
}
```

> `refresh_token` 字段：当 Refresh Token 即将过期时（滑动过期），返回新的 Refresh Token；否则为 `null`，前端无需更新。

**失败响应**：

```json
{
    "status": "error",
    "message": "刷新令牌无效或已过期",
    "error_code": "AUTHENTICATION_FAILED",
    "data": {}
}
```

### 2.6 认证错误码规范

所有认证相关错误统一使用 `AuthenticationException`，返回 BaseResponse 格式，通过 `error_code` 区分类型：

| 场景 | error_code | message | 前端处理 |
|------|-----------|---------|---------|
| Access Token 过期 | `TOKEN_EXPIRED` | "访问令牌已过期" | 自动刷新 Token |
| Token 无效/篡改 | `INVALID_TOKEN` | "无效的访问令牌" | 跳转登录页 |
| 未提供 Token | `AUTHENTICATION_FAILED` | "未提供认证凭证" | 跳转登录页 |
| 用户名密码错误 | `AUTHENTICATION_FAILED` | "用户名或密码错误，还可尝试7次" | 展示消息 |
| IP 被封锁 | `AUTHENTICATION_FAILED` | "登录尝试次数过多，请15分钟后重试" | 展示消息 |
| Refresh Token 过期 | `AUTHENTICATION_FAILED` | "刷新令牌无效或已过期" | 跳转登录页 |

> **核心原则**：前端用 `error_code` 做逻辑判断，用 `message` 做 UI 展示，不比较字符串。

---

## 3. 前端 Token 刷新机制

### 3.1 错误处理核心原则

后端所有认证相关错误都返回统一的 BaseResponse 格式（详见 [2.6 认证错误码规范](#26-认证错误码规范)），前端通过 `error_code` 做逻辑分支：

```
error_code === 'TOKEN_EXPIRED'         → 自动刷新 Token，用户无感知
error_code === 其他 (如 'INVALID_TOKEN') → 跳转登录页
```

### 3.2 Axios 响应拦截器

```javascript
// api/index.js

import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 15000,
})

// ==================== Token 刷新队列机制 ====================
let isRefreshing = false
let refreshSubscribers = []

function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback)
}

function onTokenRefreshed(newToken) {
  refreshSubscribers.forEach(cb => cb(newToken))
  refreshSubscribers = []
}

function onRefreshFailed(error) {
  refreshSubscribers.forEach(cb => cb(null, error))
  refreshSubscribers = []
}

// ==================== 辅助函数 ====================

/** 跳转到登录页并清除认证状态 */
function redirectToLogin() {
  const authStore = useAuthStore()
  authStore.logout()
  window.location.href = '/login'
}

/** 从 401 错误响应中解析 error_code 和 message */
function parseErrorResponse(error) {
  const data = error.response?.data || {}
  return {
    errorCode: data.error_code || '',
    message: data.message || '认证失败',
  }
}

/** 创建标准化的错误对象 */
function createApiError(message, originalError) {
  const apiError = new Error(message)
  apiError.originalError = originalError
  apiError.response = originalError.response
  return apiError
}

// ==================== 请求拦截器 ====================
api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers['Authorization'] = `Bearer ${authStore.token}`
  }
  return config
})

// ==================== 响应拦截器 ====================
api.interceptors.response.use(
  (response) => response.data,  // 成功时直接返回 BaseResponse
  async (error) => {
    const authStore = useAuthStore()
    const originalRequest = error.config

    // 非 401 错误直接抛出
    if (error.response?.status !== 401) {
      return Promise.reject(error)
    }

    const { errorCode, message } = parseErrorResponse(error)

    // 登录请求返回 401 → 直接展示后端消息（含剩余次数等提示）
    if (originalRequest.url.includes('/auth/login') ||
        originalRequest.url.includes('/auth/token')) {
      return Promise.reject(createApiError(message, error))
    }

    // 刷新请求返回 401 → Refresh Token 也失效了
    if (originalRequest.url.includes('/auth/refresh')) {
      redirectToLogin()
      return Promise.reject(createApiError(message, error))
    }

    // 已重试过，不再重试
    if (originalRequest._retry) {
      redirectToLogin()
      return Promise.reject(createApiError(message, error))
    }

    // ★ 核心判断：只有 TOKEN_EXPIRED 才尝试刷新
    if (errorCode === 'TOKEN_EXPIRED' && authStore.refreshToken) {
      // 并发请求合并：已在刷新中，加入等待队列
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((newToken, err) => {
            if (err) {
              reject(err)
            } else if (newToken) {
              originalRequest.headers['Authorization'] = `Bearer ${newToken}`
              originalRequest._retry = true
              resolve(api(originalRequest))
            }
          })
        })
      }

      isRefreshing = true
      try {
        const refreshSuccess = await authStore.refreshAccessToken()
        isRefreshing = false

        if (refreshSuccess) {
          onTokenRefreshed(authStore.token)
          originalRequest.headers['Authorization'] = `Bearer ${authStore.token}`
          originalRequest._retry = true
          return api(originalRequest)
        }
      } catch (refreshError) {
        isRefreshing = false
        onRefreshFailed(refreshError)
      }

      redirectToLogin()
      return Promise.reject(createApiError('登录已过期，请重新登录', error))
    }

    // 其他 401 错误（INVALID_TOKEN / AUTHENTICATION_FAILED）→ 跳转登录
    redirectToLogin()
    return Promise.reject(createApiError(message, error))
  }
)
```

### 3.3 Auth Store 刷新方法

```javascript
// stores/auth.js

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const refreshToken = ref(localStorage.getItem('refreshToken') || '')
  const userInfo = ref(null)

  /**
   * 使用 Refresh Token 刷新 Access Token
   * 
   * 注意：refresh_token 通过请求体传递（非 query 参数）
   * @returns {Promise<boolean>} 刷新是否成功
   */
  const refreshAccessToken = async () => {
    if (!refreshToken.value) return false

    try {
      // ★ 通过请求体传递 refresh_token
      const response = await api.post('/v1/auth/refresh', {
        refresh_token: refreshToken.value
      })

      // response 是 BaseResponse（拦截器已解包）:
      // { status: "success", message: "...", data: { access_token, refresh_token, token_type } }
      const { access_token, refresh_token: newRefreshToken } = response.data

      if (!access_token) return false

      // 更新 Access Token
      token.value = access_token
      localStorage.setItem('token', access_token)

      // 如果返回了新的 Refresh Token（滑动过期续期），也更新它
      if (newRefreshToken) {
        refreshToken.value = newRefreshToken
        localStorage.setItem('refreshToken', newRefreshToken)
      }

      return true
    } catch (error) {
      logout()
      return false
    }
  }

  const logout = () => {
    token.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('userInfo')
  }

  return {
    token,
    refreshToken,
    userInfo,
    refreshAccessToken,
    logout,
    // ... 其他方法
  }
})
```

### 3.4 数据流说明

```
后端 API 返回 (HTTP 200):
{
    "status": "success",
    "message": "刷新令牌成功",
    "msg_details": [],
    "data": {
        "access_token": "xxx",
        "refresh_token": "xxx",   ← 滑动续期时有值，否则 null
        "token_type": "bearer"
    }
}
        ↓
Axios 响应拦截器 response.data（已解包第一层）:
{
    "status": "success",
    "message": "刷新令牌成功",
    "data": { "access_token": "xxx", "refresh_token": "xxx", "token_type": "bearer" }
}
        ↓
前端从 response.data 解构:
const { access_token, refresh_token: newRefreshToken } = response.data
```

**错误数据流**：

```
后端 API 返回 (HTTP 401):
{
    "status": "error",
    "message": "访问令牌已过期",
    "error_code": "TOKEN_EXPIRED",        ← 前端用此字段做逻辑判断
    "data": {}
}
        ↓
Axios 响应拦截器 error.response.data:
{
    "status": "error",
    "message": "访问令牌已过期",           ← 前端用此字段做 UI 展示
    "error_code": "TOKEN_EXPIRED"
}
        ↓
拦截器判断: errorCode === 'TOKEN_EXPIRED' → 自动刷新，不打扰用户
```

---

## 4. 配置说明

### 4.1 后端 JWT 配置

```yaml
# config/settings.yaml

jwt:
  secret_key: "your-secret-key-change-this-in-production"
  algorithm: HS256
  access_token_expire_minutes: 30     # Access Token 有效期（分钟）
  refresh_token_expire_days: 7        # Refresh Token 基础有效期（天）
  refresh_token_sliding_days: 2       # 滑动过期阈值（天）
```

**滑动过期说明**：当 Refresh Token 剩余有效期少于 `refresh_token_sliding_days` 时，刷新 API 会返回新的 Refresh Token，实现"无感知"续期。

### 4.2 前端环境配置

```env
# .env
VITE_API_BASE_URL=http://localhost:8000/api
```

---

## 5. 完整示例

### 5.1 后端完整配置

```python
# app/api/v1/__init__.py

from fastapi import APIRouter
from .auth import router as auth_router
from .organizations import router as org_router
from .users import router as users_router

api_router = APIRouter()

# 公开路由（无需认证）
api_router.include_router(auth_router)

# 需要认证的路由
api_router.include_router(org_router)
api_router.include_router(users_router)
```

```python
# app/api/v1/organizations.py

from fastapi import APIRouter, Depends
from app.api.dependencies import auth

# 路由级别认证
router = APIRouter(
    prefix="/org",
    tags=["组织架构"],
    dependencies=[Depends(auth.get_current_user)]
)

@router.get("/list")
def org_list():
    """获取组织列表 - 需要认证"""
    ...
```

### 5.2 前端完整配置

```javascript
// main.js

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 恢复认证状态
const authStore = useAuthStore()
authStore.restoreAuthState()

app.mount('#app')
```

---

## 6. 常见问题排查

### 6.1 Token 刷新失败

**症状**：Access Token 过期后直接跳转到登录页，没有自动刷新。

**排查步骤**：

1. 打开浏览器 DevTools → Network 面板，查看失败的请求响应
2. 确认 401 响应中 `error_code` 是否为 `TOKEN_EXPIRED`（只有这个才会触发刷新）
3. 检查 localStorage 中是否有 `refreshToken`
4. 检查 `/v1/auth/refresh` 请求是否发出及其响应

**常见原因**：

| 原因 | 解决方案 |
|------|---------|
| Refresh Token 未保存 | 检查登录时是否正确保存到 localStorage |
| Refresh Token 过期 | 检查后端 `refresh_token_expire_days` 配置 |
| 401 响应缺少 `error_code` | 检查后端是否使用 `AuthenticationException` 而非 `HTTPException` |
| 刷新接口传参方式不对 | 确认使用请求体 `{ refresh_token: "xxx" }` 而非 query 参数 |
| 拦截器未按 `error_code` 判断 | 确认用 `error_code === 'TOKEN_EXPIRED'` 而非比较 message 字符串 |

### 6.2 登录失败消息不正确

**症状**：登录失败时前端显示兜底消息而非后端提示。

**排查要点**：

```javascript
// ✅ 正确：使用后端返回的 message
const { message } = parseErrorResponse(error)
ElMessage.error(message)  // "用户名或密码错误，还可尝试7次"

// ❌ 错误：硬编码字符串
ElMessage.error('用户名或密码错误')
```

### 6.3 添加调试日志

在 `auth.js` 的 `refreshAccessToken` 方法中添加详细日志：

```javascript
const refreshAccessToken = async () => {
  console.log('========== 开始刷新 Token ==========')
  console.log('当前 refreshToken:', refreshToken.value ? '存在' : '不存在')

  try {
    // ★ 注意是请求体，不是 query 参数
    const response = await api.post('/v1/auth/refresh', {
      refresh_token: refreshToken.value
    })

    console.log('刷新响应:', response)
    console.log('response.data:', response.data)

    const { access_token, refresh_token: newRefreshToken } = response.data
    console.log('解析后 access_token:', access_token ? '存在' : 'undefined')
    console.log('是否有新 refreshToken:', !!newRefreshToken)

    // ...
  } catch (error) {
    console.error('刷新失败:', error.message)
    console.error('error_code:', error.response?.data?.error_code)
  }
}
```

### 6.4 测试 Token 刷新

将 Access Token 有效期临时设置为 1 分钟，便于测试：

```yaml
# config/settings.yaml

jwt:
  access_token_expire_minutes: 1  # 测试用，正式环境改回 30
```

**测试步骤**：

1. 重启后端服务
2. 重新登录
3. 打开浏览器 DevTools（Console + Network）
4. 等待 1 分钟后操作页面
5. 观察 Network 面板：应看到一次 401 响应（`TOKEN_EXPIRED`），然后自动发出 `/auth/refresh` 请求，最后重试原请求成功

---

## 7. 最佳实践总结

### 后端

| 规范 | 说明 |
|------|------|
| 使用路由级别认证 | 在 `APIRouter(dependencies=[...])` 中添加 |
| 分离公开路由 | 登录、刷新等接口使用单独的路由器 |
| 返回标准格式 | 使用 `OK(result)` 返回 BaseResponse 格式 |
| 支持滑动过期 | Refresh Token 快过期时自动续期 |
| 统一认证异常 | 使用 `AuthenticationException` 而非 `HTTPException`，确保返回 `error_code` |

### 前端

| 规范 | 说明 |
|------|------|
| 用 `error_code` 做逻辑判断 | 只有 `TOKEN_EXPIRED` 触发自动刷新，其他 401 跳转登录 |
| 用 `message` 做 UI 展示 | 直接显示后端返回的消息，不硬编码字符串 |
| refresh_token 通过请求体传递 | `api.post('/v1/auth/refresh', { refresh_token })` |
| 请求队列机制 | 多个请求同时 401 时只刷新一次，其他排队等待 |
| 持久化存储 | Token 保存到 localStorage |

### 数据格式一致性

```
成功响应:
  后端返回: { status: "success", message, data: { access_token, refresh_token, token_type } }
                                                          ↓
  前端解析: response.data → { access_token, refresh_token, token_type }

错误响应:
  后端返回: { status: "error", message: "可展示的消息", error_code: "TOKEN_EXPIRED" }
                                          ↓                              ↓
  前端展示: message → UI 提示              前端逻辑: error_code → 刷新 or 跳转
```
