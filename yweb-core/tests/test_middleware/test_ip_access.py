"""IP 访问控制中间件测试

测试 IPAccessMiddleware、IPAccessRule、IPAllow、IPDeny 的完整功能
"""

import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from yweb.middleware.ip_access import IPAccessMiddleware, IPAccessRule, IPAllow, IPDeny


# ==================== Fixtures ====================

@pytest.fixture
def base_app():
    """创建基础 FastAPI 应用（不带中间件）"""
    app = FastAPI()

    @app.get("/")
    def root():
        return {"message": "ok"}

    @app.get("/api/v1/admin/users")
    def admin_users():
        return {"users": []}

    @app.get("/api/v1/admin/settings")
    def admin_settings():
        return {"settings": {}}

    @app.get("/api/v1/public/info")
    def public_info():
        return {"info": "public"}

    @app.get("/api/v1/oauth2/token")
    def oauth2_token():
        return {"token": "xxx"}

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    return app


def _create_client(app, middleware_kwargs):
    """为 app 添加中间件并返回 TestClient"""
    app.add_middleware(IPAccessMiddleware, **middleware_kwargs)
    return TestClient(app)


# ==================== 基础功能测试 ====================

class TestIPAccessMiddlewareBasic:
    """IPAccessMiddleware 基本功能测试"""

    def test_no_rules_allows_all(self, base_app):
        """测试无规则时允许所有请求"""
        client = _create_client(base_app, {"rules": []})

        response = client.get("/")
        assert response.status_code == 200

    def test_no_rules_default_deny(self, base_app):
        """测试默认策略 deny + 无规则时拒绝所有请求"""
        client = _create_client(base_app, {
            "rules": [],
            "default_policy": "deny",
        })

        response = client.get("/")
        assert response.status_code == 403

    def test_non_http_passes_through(self):
        """测试非 HTTP 请求直接通过"""
        app = FastAPI()
        middleware = IPAccessMiddleware(
            app,
            rules=[IPAccessRule(paths=["/*"], deny_ips=["*"])],
        )
        # 非 http scope 类型应直接通过，不做 IP 检查
        # 这里无法直接用 TestClient 测试 websocket，仅验证构造不报错
        assert middleware is not None


# ==================== 白名单测试 ====================

class TestWhitelistRules:
    """白名单规则测试（TestClient 集成）"""

    def test_whitelist_wildcard_allows_all(self, base_app):
        """测试白名单通配符 * 允许所有 IP（包括 TestClient）"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["*"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 200

    def test_whitelist_reject_when_not_in_list(self, base_app):
        """测试不在白名单中的 IP 被拒绝"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

    def test_whitelist_cidr_reject(self, base_app):
        """测试不在 CIDR 白名单中的 IP 被拒绝"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["192.168.0.0/16"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

    def test_whitelist_only_affects_matched_paths(self, base_app):
        """测试白名单规则仅影响匹配的路径"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        # 管理路径被拒绝
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # 非管理路径不受影响（default_policy=allow）
        response = client.get("/api/v1/public/info")
        assert response.status_code == 200

        response = client.get("/health")
        assert response.status_code == 200


# ==================== 黑名单测试 ====================

class TestBlacklistRules:
    """黑名单规则测试（TestClient 集成）"""

    def test_blacklist_wildcard_denies_all(self, base_app):
        """测试黑名单通配符 * 拒绝所有 IP"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    deny_ips=["*"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

    def test_blacklist_not_matched_allows(self, base_app):
        """测试不在黑名单中的 IP 被放行"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    deny_ips=["10.0.0.1"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 200


# ==================== 混合规则测试 ====================

class TestMixedRules:
    """同时配置黑名单和白名单的规则测试（TestClient 集成）"""

    def test_deny_wildcard_takes_priority_over_allow(self, base_app):
        """测试黑名单通配符优先于白名单通配符"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["*"],
                    deny_ips=["*"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

    def test_not_in_deny_and_in_allow_wildcard(self, base_app):
        """测试不在黑名单且在白名单通配符中 → 放行"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["*"],
                    deny_ips=["10.0.0.1"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 200


# ==================== 路径匹配测试 ====================

class TestPathMatching:
    """路径匹配测试"""

    def test_wildcard_path(self, base_app):
        """测试通配符路径匹配"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        # /api/v1/admin/users 匹配 /api/v1/admin/*
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # /api/v1/admin/settings 也匹配
        response = client.get("/api/v1/admin/settings")
        assert response.status_code == 403

    def test_exact_path(self, base_app):
        """测试精确路径匹配"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/users"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        # 精确匹配 → 被规则控制
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # 其他路径不受影响
        response = client.get("/api/v1/admin/settings")
        assert response.status_code == 200

    def test_multiple_path_patterns(self, base_app):
        """测试同一规则多个路径模式"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*", "/api/v1/oauth2/*"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        response = client.get("/api/v1/oauth2/token")
        assert response.status_code == 403

        # 其他路径不受影响
        response = client.get("/api/v1/public/info")
        assert response.status_code == 200


# ==================== 多规则测试 ====================

class TestMultipleRules:
    """多条规则交互测试"""

    def test_first_match_wins(self, base_app):
        """测试第一个匹配的规则生效"""
        client = _create_client(base_app, {
            "rules": [
                # 规则1：admin 路径，仅允许 10.0.0.1
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["10.0.0.1"],
                ),
                # 规则2：更宽泛，允许所有
                IPAccessRule(
                    paths=["/api/v1/*"],
                    allow_ips=["*"],
                ),
            ],
        })

        # admin 路径命中规则1（白名单不含 TestClient IP），被拒绝
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # public 路径不匹配规则1，命中规则2（通配符），被放行
        response = client.get("/api/v1/public/info")
        assert response.status_code == 200

    def test_different_rules_for_different_paths(self, base_app):
        """测试不同路径使用不同规则"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    deny_ips=["*"],
                    description="管理后台拒绝所有",
                ),
                IPAccessRule(
                    paths=["/api/v1/oauth2/*"],
                    allow_ips=["*"],
                    description="OAuth2 对外开放",
                ),
            ],
        })

        # admin 被拒绝
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # oauth2 被放行
        response = client.get("/api/v1/oauth2/token")
        assert response.status_code == 200


# ==================== 拒绝响应测试 ====================

class TestDenyResponse:
    """拒绝响应格式测试"""

    def test_default_deny_response(self, base_app):
        """测试默认拒绝响应格式"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/*"], allow_ips=["10.0.0.1"]),
            ],
        })

        response = client.get("/")
        assert response.status_code == 403
        data = response.json()
        assert "code" in data
        assert "message" in data
        assert data["code"] == 403

    def test_custom_deny_status_code(self, base_app):
        """测试自定义拒绝状态码"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/*"], allow_ips=["10.0.0.1"]),
            ],
            "deny_status_code": 451,
        })

        response = client.get("/")
        assert response.status_code == 451

    def test_custom_deny_message(self, base_app):
        """测试自定义拒绝消息"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/*"], allow_ips=["10.0.0.1"]),
            ],
            "deny_message": "Forbidden by policy",
        })

        response = client.get("/")
        data = response.json()
        assert data["message"] == "Forbidden by policy"

    def test_deny_response_content_type(self, base_app):
        """测试拒绝响应的 Content-Type"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/*"], allow_ips=["10.0.0.1"]),
            ],
        })

        response = client.get("/")
        assert "application/json" in response.headers.get("content-type", "")


# ==================== from_settings 测试 ====================

class TestFromSettings:
    """from_settings 静态方法测试"""

    def test_from_dict_basic(self):
        """测试从字典加载基本配置"""
        config = {
            "enabled": True,
            "default_policy": "deny",
            "trusted_proxies": ["127.0.0.1"],
            "rules": [
                {
                    "paths": ["/api/admin/*"],
                    "allow_ips": ["192.168.0.0/16"],
                    "description": "仅内网",
                },
            ],
        }

        result = IPAccessMiddleware.from_settings(config)

        assert result["default_policy"] == "deny"
        assert result["trusted_proxies"] == ["127.0.0.1"]
        assert len(result["rules"]) == 1
        assert result["rules"][0].paths == ["/api/admin/*"]
        assert result["rules"][0].allow_ips == ["192.168.0.0/16"]
        assert result["rules"][0].description == "仅内网"

    def test_from_dict_disabled(self):
        """测试 enabled=false 时返回空规则"""
        config = {
            "enabled": False,
            "rules": [
                {"paths": ["/api/*"], "allow_ips": ["10.0.0.1"]},
            ],
        }

        result = IPAccessMiddleware.from_settings(config)
        assert result["rules"] == []

    def test_from_dict_defaults(self):
        """测试缺省值"""
        config = {
            "rules": [
                {"paths": ["/test"]},
            ],
        }

        result = IPAccessMiddleware.from_settings(config)
        assert result["default_policy"] == "allow"
        assert result["deny_status_code"] == 403
        assert result["deny_message"] == "IP 访问被拒绝"
        assert len(result["rules"]) == 1
        assert result["rules"][0].allow_ips == []
        assert result["rules"][0].deny_ips == []

    def test_from_dict_empty_rules(self):
        """测试空规则列表"""
        config = {"rules": []}

        result = IPAccessMiddleware.from_settings(config)
        assert result["rules"] == []

    def test_from_dict_no_rules_key(self):
        """测试没有 rules 键"""
        config = {"default_policy": "deny"}

        result = IPAccessMiddleware.from_settings(config)
        assert result["rules"] == []

    def test_from_invalid_config(self):
        """测试无效配置返回空规则"""
        result = IPAccessMiddleware.from_settings(42)
        assert result == {"rules": []}

        result = IPAccessMiddleware.from_settings(None)
        assert result == {"rules": []}

    def test_from_dict_custom_deny(self):
        """测试自定义拒绝响应配置"""
        config = {
            "deny_status_code": 451,
            "deny_message": "Blocked",
            "rules": [],
        }

        result = IPAccessMiddleware.from_settings(config)
        assert result["deny_status_code"] == 451
        assert result["deny_message"] == "Blocked"

    def test_from_dict_multiple_rules(self):
        """测试多条规则加载"""
        config = {
            "rules": [
                {"paths": ["/admin/*"], "allow_ips": ["10.0.0.0/8"]},
                {"paths": ["/api/*"], "deny_ips": ["1.2.3.4"]},
                {"paths": ["/public/*"], "allow_ips": ["*"], "description": "公开"},
            ],
        }

        result = IPAccessMiddleware.from_settings(config)
        assert len(result["rules"]) == 3
        assert result["rules"][0].allow_ips == ["10.0.0.0/8"]
        assert result["rules"][1].deny_ips == ["1.2.3.4"]
        assert result["rules"][2].description == "公开"

    def test_from_settings_integrated(self, base_app):
        """测试 from_settings → add_middleware 完整集成"""
        config = {
            "enabled": True,
            "default_policy": "allow",
            "rules": [
                {
                    "paths": ["/api/v1/admin/*"],
                    "allow_ips": ["10.0.0.1"],
                    "description": "管理后台限内网",
                },
            ],
        }

        kwargs = IPAccessMiddleware.from_settings(config)
        client = _create_client(base_app, kwargs)

        # admin 被拒绝（TestClient IP 不在白名单中）
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

        # 其他路径正常
        response = client.get("/health")
        assert response.status_code == 200


# ==================== IPAccessRule 测试 ====================

class TestIPAccessRule:
    """IPAccessRule 数据类测试"""

    def test_default_values(self):
        """测试默认值"""
        rule = IPAccessRule(paths=["/test"])
        assert rule.paths == ["/test"]
        assert rule.allow_ips == []
        assert rule.deny_ips == []
        assert rule.description == ""

    def test_full_values(self):
        """测试完整赋值"""
        rule = IPAccessRule(
            paths=["/api/*"],
            allow_ips=["10.0.0.0/8"],
            deny_ips=["10.0.0.1"],
            description="测试规则",
        )
        assert rule.paths == ["/api/*"]
        assert rule.allow_ips == ["10.0.0.0/8"]
        assert rule.deny_ips == ["10.0.0.1"]
        assert rule.description == "测试规则"


# ==================== _check_access 核心逻辑测试（使用合法 IP） ====================

class TestCheckAccessLogic:
    """直接测试 _check_access 方法，使用合法 IP 覆盖完整的匹配逻辑

    注意：TestClient 默认 IP 为 "testclient"（非合法 IP），
    无法测试具体 IP/CIDR 匹配，因此这里直接调用中间件内部方法。
    """

    @pytest.fixture
    def middleware(self):
        """创建一个带规则的中间件实例"""
        from fastapi import FastAPI
        app = FastAPI()
        return IPAccessMiddleware(
            app,
            rules=[
                IPAccessRule(
                    paths=["/api/v1/admin/*"],
                    allow_ips=["192.168.0.0/16", "10.0.0.1"],
                    description="管理后台仅内网",
                ),
                IPAccessRule(
                    paths=["/api/v1/internal/*"],
                    deny_ips=["203.0.113.0/24"],
                    description="内部接口黑名单",
                ),
                IPAccessRule(
                    paths=["/api/v1/mixed/*"],
                    allow_ips=["10.0.0.0/8"],
                    deny_ips=["10.0.0.99"],
                    description="混合规则",
                ),
                IPAccessRule(
                    paths=["/api/v1/oauth2/*"],
                    allow_ips=["*"],
                    description="OAuth2 公开",
                ),
            ],
        )

    # --- 白名单 ---

    def test_whitelist_single_ip_allow(self, middleware):
        """白名单：精确 IP 匹配 → 放行"""
        allowed, _ = middleware._check_access("10.0.0.1", "/api/v1/admin/users")
        assert allowed is True

    def test_whitelist_cidr_allow(self, middleware):
        """白名单：CIDR 网段匹配 → 放行"""
        allowed, _ = middleware._check_access("192.168.100.5", "/api/v1/admin/users")
        assert allowed is True

    def test_whitelist_not_in_list_deny(self, middleware):
        """白名单：IP 不在列表中 → 拒绝"""
        allowed, _ = middleware._check_access("8.8.8.8", "/api/v1/admin/users")
        assert allowed is False

    def test_whitelist_wildcard_allow(self, middleware):
        """白名单通配符：任何 IP 都放行"""
        allowed, _ = middleware._check_access("1.2.3.4", "/api/v1/oauth2/token")
        assert allowed is True

    # --- 黑名单 ---

    def test_blacklist_cidr_deny(self, middleware):
        """黑名单：CIDR 网段匹配 → 拒绝"""
        allowed, _ = middleware._check_access("203.0.113.50", "/api/v1/internal/data")
        assert allowed is False

    def test_blacklist_not_in_list_allow(self, middleware):
        """黑名单：IP 不在黑名单中 → 放行"""
        allowed, _ = middleware._check_access("8.8.8.8", "/api/v1/internal/data")
        assert allowed is True

    # --- 混合规则（同时有 allow 和 deny） ---

    def test_mixed_deny_takes_priority(self, middleware):
        """混合规则：在黑名单中（即使在白名单网段内）→ 拒绝"""
        allowed, _ = middleware._check_access("10.0.0.99", "/api/v1/mixed/action")
        assert allowed is False

    def test_mixed_not_in_deny_in_allow(self, middleware):
        """混合规则：不在黑名单且在白名单中 → 放行"""
        allowed, _ = middleware._check_access("10.0.0.1", "/api/v1/mixed/action")
        assert allowed is True

    def test_mixed_not_in_deny_not_in_allow(self, middleware):
        """混合规则：不在黑名单但也不在白名单中 → 拒绝"""
        allowed, _ = middleware._check_access("172.16.0.1", "/api/v1/mixed/action")
        assert allowed is False

    # --- 路径不匹配任何规则 ---

    def test_unmatched_path_default_allow(self, middleware):
        """不匹配任何规则的路径 → 默认放行"""
        allowed, _ = middleware._check_access("8.8.8.8", "/health")
        assert allowed is True

    def test_unmatched_path_default_deny(self):
        """不匹配任何规则的路径 + default_policy=deny → 拒绝"""
        from fastapi import FastAPI
        app = FastAPI()
        mw = IPAccessMiddleware(app, rules=[], default_policy="deny")
        allowed, _ = mw._check_access("8.8.8.8", "/anything")
        assert allowed is False


# ==================== 边界场景测试 ====================

class TestEdgeCases:
    """边界场景测试"""

    def test_root_path_rule(self, base_app):
        """测试根路径规则"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/"], allow_ips=["10.0.0.1"]),
            ],
        })

        # 精确匹配根路径 → 拒绝
        response = client.get("/")
        assert response.status_code == 403

        # 其他路径不受影响
        response = client.get("/health")
        assert response.status_code == 200

    def test_empty_allow_and_deny(self, base_app):
        """测试 allow_ips 和 deny_ips 都为空的规则（相当于无约束）"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(paths=["/api/v1/admin/*"]),
            ],
            "default_policy": "deny",
        })

        # 匹配到规则，但无 allow 也无 deny
        # _check_access 中：匹配规则但 allow_ips 和 deny_ips 都为空
        # → 不会进入任何 if 分支，会继续遍历
        # → 最终走 default_policy（deny）
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403

    def test_health_check_not_blocked(self, base_app):
        """测试健康检查路径不受管理规则影响"""
        client = _create_client(base_app, {
            "rules": [
                IPAccessRule(
                    paths=["/api/*"],
                    allow_ips=["10.0.0.1"],
                ),
            ],
        })

        # /health 不匹配 /api/*
        response = client.get("/health")
        assert response.status_code == 200

        # /api/ 下的路径被控制
        response = client.get("/api/v1/admin/users")
        assert response.status_code == 403


# ==================== 路由级别 IPAllow 依赖测试 ====================

class TestIPAllow:
    """IPAllow 路由级白名单依赖测试"""

    @pytest.fixture
    def app_with_ip_allow(self):
        """创建带 IPAllow 依赖的应用"""
        app = FastAPI()

        @app.get("/open")
        def open_endpoint():
            return {"access": "open"}

        @app.post(
            "/admin/sync",
            dependencies=[Depends(IPAllow(["10.0.0.0/8"]))],
        )
        def admin_sync():
            return {"synced": True}

        @app.get(
            "/admin/wildcard",
            dependencies=[Depends(IPAllow(["*"]))],
        )
        def admin_wildcard():
            return {"access": "wildcard"}

        return app

    def test_allow_wildcard(self, app_with_ip_allow):
        """测试通配符 * 允许所有 IP"""
        client = TestClient(app_with_ip_allow)

        response = client.get("/admin/wildcard")
        assert response.status_code == 200
        assert response.json()["access"] == "wildcard"

    def test_deny_when_not_in_whitelist(self, app_with_ip_allow):
        """测试不在白名单中的 IP 被拒绝"""
        client = TestClient(app_with_ip_allow)

        response = client.post("/admin/sync")
        assert response.status_code == 403

    def test_open_endpoint_not_affected(self, app_with_ip_allow):
        """测试没有 IPAllow 的端点不受影响"""
        client = TestClient(app_with_ip_allow)

        response = client.get("/open")
        assert response.status_code == 200

    def test_custom_deny_status_code(self):
        """测试自定义拒绝状态码"""
        app = FastAPI()

        @app.get(
            "/strict",
            dependencies=[Depends(IPAllow(["10.0.0.1"], deny_status_code=451))],
        )
        def strict():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/strict")
        assert response.status_code == 451

    def test_custom_deny_message(self):
        """测试自定义拒绝消息"""
        app = FastAPI()

        @app.get(
            "/strict",
            dependencies=[Depends(IPAllow(["10.0.0.1"], deny_message="Nope"))],
        )
        def strict():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/strict")
        assert response.status_code == 403
        assert response.json()["detail"] == "Nope"

    def test_router_level_ip_allow(self):
        """测试 Router 级别的 IPAllow"""
        from fastapi import APIRouter

        app = FastAPI()
        router = APIRouter(
            prefix="/internal",
            dependencies=[Depends(IPAllow(["10.0.0.0/8"]))],
        )

        @router.get("/data")
        def get_data():
            return {"data": "secret"}

        @router.get("/status")
        def get_status():
            return {"status": "ok"}

        app.include_router(router)

        @app.get("/public")
        def public():
            return {"public": True}

        client = TestClient(app)

        # Router 下的端点都被拒绝
        assert client.get("/internal/data").status_code == 403
        assert client.get("/internal/status").status_code == 403

        # Router 外的端点不受影响
        assert client.get("/public").status_code == 200


# ==================== 路由级别 IPDeny 依赖测试 ====================

class TestIPDeny:
    """IPDeny 路由级黑名单依赖测试"""

    def test_deny_wildcard_blocks_all(self):
        """测试黑名单通配符 * 拒绝所有"""
        app = FastAPI()

        @app.get("/blocked", dependencies=[Depends(IPDeny(["*"]))])
        def blocked():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/blocked")
        assert response.status_code == 403

    def test_deny_specific_ip_not_matched(self):
        """测试不在黑名单中的 IP 放行"""
        app = FastAPI()

        @app.get("/data", dependencies=[Depends(IPDeny(["1.2.3.4"]))])
        def data():
            return {"data": "ok"}

        client = TestClient(app)
        response = client.get("/data")
        assert response.status_code == 200

    def test_deny_with_allow_exception(self):
        """测试黑名单 + 白名单豁免"""
        app = FastAPI()

        # 拒绝所有，但允许通配符（模拟"拒绝所有但允许特定 IP"）
        @app.get(
            "/debug",
            dependencies=[Depends(IPDeny(["*"], allow_ips=["*"]))],
        )
        def debug():
            return {"debug": True}

        client = TestClient(app)
        # 白名单优先 → 放行
        response = client.get("/debug")
        assert response.status_code == 200

    def test_deny_allow_exception_specific(self):
        """测试黑名单全拒绝 + 白名单不含当前 IP → 拒绝"""
        app = FastAPI()

        @app.get(
            "/debug",
            dependencies=[Depends(IPDeny(["*"], allow_ips=["127.0.0.1"]))],
        )
        def debug():
            return {"debug": True}

        client = TestClient(app)
        # TestClient IP (testclient) 不在 allow_ips 中 → 拒绝
        response = client.get("/debug")
        assert response.status_code == 403

    def test_custom_status_and_message(self):
        """测试自定义状态码和消息"""
        app = FastAPI()

        @app.get(
            "/forbidden",
            dependencies=[Depends(IPDeny(
                ["*"],
                deny_status_code=451,
                deny_message="Legally blocked",
            ))],
        )
        def forbidden():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/forbidden")
        assert response.status_code == 451
        assert response.json()["detail"] == "Legally blocked"


# ==================== IPAllow + IPDeny 组合测试 ====================

class TestIPAllowDenyCombined:
    """IPAllow 和 IPDeny 组合使用测试"""

    def test_multiple_dependencies(self):
        """测试同一路由同时使用 IPAllow 和 IPDeny"""
        app = FastAPI()

        # 白名单通配符放行 + 黑名单通配符拒绝 → 先执行 IPAllow（通过），再执行 IPDeny（拒绝）
        @app.get(
            "/test",
            dependencies=[
                Depends(IPAllow(["*"])),
                Depends(IPDeny(["*"])),
            ],
        )
        def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/test")
        # IPAllow 通过，但 IPDeny 拒绝
        assert response.status_code == 403

    def test_endpoint_without_ip_deps_unaffected(self):
        """测试无 IP 依赖的端点不受影响"""
        app = FastAPI()

        @app.get("/protected", dependencies=[Depends(IPAllow(["10.0.0.1"]))])
        def protected():
            return {"protected": True}

        @app.get("/free")
        def free():
            return {"free": True}

        client = TestClient(app)
        assert client.get("/protected").status_code == 403
        assert client.get("/free").status_code == 200


# ==================== @ip_allow 装饰器测试 ====================

from yweb.middleware.ip_access import ip_allow, ip_deny


class TestIpAllowDecorator:
    """@ip_allow 装饰器测试"""

    def test_wildcard_allows_all(self):
        """测试 @ip_allow(["*"]) 允许所有 IP"""
        app = FastAPI()

        @app.get("/open")
        @ip_allow(["*"])
        async def open_endpoint():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/open").status_code == 200
        assert client.get("/open").json() == {"ok": True}

    def test_specific_ip_rejects_others(self):
        """测试指定 IP 白名单拒绝不在列表中的 IP"""
        app = FastAPI()

        @app.get("/internal")
        @ip_allow(["10.0.0.0/8"])
        async def internal():
            return {"data": "secret"}

        client = TestClient(app)
        assert client.get("/internal").status_code == 403

    def test_custom_status_and_message(self):
        """测试自定义状态码和消息"""
        app = FastAPI()

        @app.get("/strict")
        @ip_allow(["10.0.0.1"], status_code=451, message="Blocked")
        async def strict():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/strict")
        assert resp.status_code == 451
        assert resp.json()["detail"] == "Blocked"

    def test_does_not_break_path_params(self):
        """测试装饰器不破坏 Path 参数注入"""
        app = FastAPI()

        @app.get("/users/{user_id}")
        @ip_allow(["*"])
        async def get_user(user_id: int):
            return {"user_id": user_id}

        client = TestClient(app)
        resp = client.get("/users/42")
        assert resp.status_code == 200
        assert resp.json() == {"user_id": 42}

    def test_does_not_break_query_params(self):
        """测试装饰器不破坏 Query 参数注入"""
        app = FastAPI()

        @app.get("/search")
        @ip_allow(["*"])
        async def search(q: str = "default", page: int = 1):
            return {"q": q, "page": page}

        client = TestClient(app)
        resp = client.get("/search?q=hello&page=3")
        assert resp.status_code == 200
        assert resp.json() == {"q": "hello", "page": 3}

    def test_does_not_break_body_params(self):
        """测试装饰器不破坏 Body 参数注入"""
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str

        app = FastAPI()

        @app.post("/items")
        @ip_allow(["*"])
        async def create_item(item: Item):
            return {"name": item.name}

        client = TestClient(app)
        resp = client.post("/items", json={"name": "test"})
        assert resp.status_code == 200
        assert resp.json() == {"name": "test"}

    def test_works_with_existing_request_param(self):
        """测试原函数已有 request 参数时正常工作"""
        app = FastAPI()

        @app.get("/with-request")
        @ip_allow(["*"])
        async def with_request(request: Request):
            return {"path": request.url.path}

        client = TestClient(app)
        resp = client.get("/with-request")
        assert resp.status_code == 200
        assert resp.json() == {"path": "/with-request"}

    def test_works_with_sync_function(self):
        """测试同步函数也能正常工作"""
        app = FastAPI()

        @app.get("/sync")
        @ip_allow(["*"])
        def sync_endpoint():
            return {"sync": True}

        client = TestClient(app)
        resp = client.get("/sync")
        assert resp.status_code == 200
        assert resp.json() == {"sync": True}

    def test_undecorated_endpoint_not_affected(self):
        """测试未加装饰器的端点不受影响"""
        app = FastAPI()

        @app.get("/guarded")
        @ip_allow(["10.0.0.1"])
        async def guarded():
            return {"guarded": True}

        @app.get("/free")
        async def free():
            return {"free": True}

        client = TestClient(app)
        assert client.get("/guarded").status_code == 403
        assert client.get("/free").status_code == 200

    def test_stacked_decorators(self):
        """测试多个装饰器叠加"""
        app = FastAPI()

        @app.get("/double")
        @ip_allow(["*"])         # 外层：白名单通配
        @ip_deny(["10.0.0.1"])   # 内层：黑名单（不影响 testclient）
        async def double():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/double")
        assert resp.status_code == 200

    def test_not_shown_in_openapi(self):
        """测试 request 参数不出现在 OpenAPI schema 中"""
        app = FastAPI()

        @app.get("/test")
        @ip_allow(["*"])
        async def test_endpoint(name: str = "world"):
            return {"hello": name}

        client = TestClient(app)
        resp = client.get("/openapi.json")
        schema = resp.json()
        # /test 的参数中不应该有 request
        params = schema["paths"]["/test"]["get"].get("parameters", [])
        param_names = [p["name"] for p in params]
        assert "request" not in param_names


# ==================== @ip_deny 装饰器测试 ====================

class TestIpDenyDecorator:
    """@ip_deny 装饰器测试"""

    def test_wildcard_denies_all(self):
        """测试 @ip_deny(["*"]) 拒绝所有 IP"""
        app = FastAPI()

        @app.get("/blocked")
        @ip_deny(["*"])
        async def blocked():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/blocked").status_code == 403

    def test_specific_ip_not_matched(self):
        """测试不在黑名单中的 IP 放行"""
        app = FastAPI()

        @app.get("/data")
        @ip_deny(["1.2.3.4"])
        async def data():
            return {"data": "ok"}

        client = TestClient(app)
        assert client.get("/data").status_code == 200

    def test_deny_with_allow_exception(self):
        """测试黑名单 + 白名单豁免"""
        app = FastAPI()

        @app.get("/debug")
        @ip_deny(["*"], allow=["*"])
        async def debug():
            return {"debug": True}

        client = TestClient(app)
        assert client.get("/debug").status_code == 200

    def test_deny_all_allow_specific_rejects(self):
        """测试拒绝所有 + 白名单不含当前 IP → 拒绝"""
        app = FastAPI()

        @app.get("/debug")
        @ip_deny(["*"], allow=["127.0.0.1"])
        async def debug():
            return {"debug": True}

        client = TestClient(app)
        assert client.get("/debug").status_code == 403

    def test_does_not_break_path_params(self):
        """测试装饰器不破坏 Path 参数"""
        app = FastAPI()

        @app.get("/items/{item_id}")
        @ip_deny(["1.2.3.4"])
        async def get_item(item_id: int):
            return {"item_id": item_id}

        client = TestClient(app)
        resp = client.get("/items/99")
        assert resp.status_code == 200
        assert resp.json() == {"item_id": 99}
