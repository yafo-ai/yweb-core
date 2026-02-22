"""LDAP/Active Directory 认证模块

提供与 LDAP/AD 目录服务的集成认证。

支持功能：
- LDAP 简单绑定认证
- Active Directory 认证
- 用户属性同步
- 组成员关系查询

使用示例:
    from yweb.auth.ldap import LDAPManager, LDAPAuthProvider
    
    # 创建 LDAP 管理器
    ldap_manager = LDAPManager(
        server="ldap://ldap.example.com:389",
        base_dn="dc=example,dc=com",
        bind_dn="cn=admin,dc=example,dc=com",
        bind_password="admin_password",
    )
    
    # 验证用户
    result = ldap_manager.authenticate(
        username="john",
        password="user_password",
    )
    
    # 获取用户信息
    user_info = ldap_manager.get_user("john")
    
    # 获取用户组
    groups = ldap_manager.get_user_groups("john")

注意：
    此模块需要安装 ldap3 库：pip install ldap3
    对于 Active Directory，建议使用 LDAPS (636 端口) 或 STARTTLS
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from enum import Enum

from .base import AuthProvider, AuthType, UserIdentity, AuthResult


# 尝试导入 ldap3
try:
    import ldap3
    from ldap3 import Server, Connection, ALL, SUBTREE, NTLM
    from ldap3.core.exceptions import LDAPException, LDAPBindError
    LDAP3_AVAILABLE = True
except ImportError:
    LDAP3_AVAILABLE = False
    ldap3 = None


class LDAPType(str, Enum):
    """LDAP 服务器类型"""
    STANDARD = "standard"  # 标准 LDAP (OpenLDAP 等)
    ACTIVE_DIRECTORY = "ad"  # Microsoft Active Directory


@dataclass
class LDAPConfig:
    """LDAP 配置
    
    Attributes:
        server: LDAP 服务器地址（如 ldap://ldap.example.com:389）
        base_dn: 基础 DN（如 dc=example,dc=com）
        bind_dn: 绑定 DN（管理员 DN）
        bind_password: 绑定密码
        ldap_type: LDAP 类型
        use_ssl: 是否使用 SSL
        use_tls: 是否使用 STARTTLS
        timeout: 连接超时（秒）
    """
    server: str
    base_dn: str
    bind_dn: Optional[str] = None
    bind_password: Optional[str] = None
    ldap_type: LDAPType = LDAPType.STANDARD
    use_ssl: bool = False
    use_tls: bool = False
    timeout: int = 10
    
    # 用户搜索配置
    user_search_base: Optional[str] = None  # 用户搜索基础 DN，默认使用 base_dn
    user_search_filter: str = "(uid={username})"  # 用户搜索过滤器
    user_dn_template: Optional[str] = None  # 用户 DN 模板（如 uid={username},ou=users,dc=example,dc=com）
    
    # 组搜索配置
    group_search_base: Optional[str] = None  # 组搜索基础 DN
    group_search_filter: str = "(member={user_dn})"  # 组成员搜索过滤器
    group_name_attribute: str = "cn"  # 组名称属性
    
    # 属性映射
    attributes_mapping: Dict[str, str] = field(default_factory=lambda: {
        "username": "uid",
        "email": "mail",
        "display_name": "displayName",
        "first_name": "givenName",
        "last_name": "sn",
        "phone": "telephoneNumber",
        "department": "department",
        "title": "title",
    })


@dataclass
class LDAPUser:
    """LDAP 用户信息"""
    dn: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    raw_attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dn": self.dn,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "department": self.department,
            "title": self.title,
            "groups": self.groups,
        }


class LDAPManager:
    """LDAP 管理器
    
    提供 LDAP 认证和用户信息查询功能。
    
    使用示例:
        # 标准 LDAP
        manager = LDAPManager(
            server="ldap://ldap.example.com:389",
            base_dn="dc=example,dc=com",
        )
        
        # Active Directory
        manager = LDAPManager(
            server="ldaps://ad.example.com:636",
            base_dn="dc=example,dc=com",
            ldap_type=LDAPType.ACTIVE_DIRECTORY,
            use_ssl=True,
        )
        
        # 验证用户
        result = manager.authenticate("john", "password")
        
        # 获取用户信息
        user = manager.get_user("john")
    """
    
    def __init__(
        self,
        server: str = None,
        base_dn: str = None,
        bind_dn: str = None,
        bind_password: str = None,
        ldap_type: LDAPType = LDAPType.STANDARD,
        use_ssl: bool = False,
        use_tls: bool = False,
        timeout: int = 10,
        config: LDAPConfig = None,
    ):
        """
        可以通过参数或 config 对象初始化。
        """
        if not LDAP3_AVAILABLE:
            raise ImportError(
                "ldap3 未安装。请运行: pip install ldap3"
            )
        
        if config:
            self.config = config
        else:
            self.config = LDAPConfig(
                server=server,
                base_dn=base_dn,
                bind_dn=bind_dn,
                bind_password=bind_password,
                ldap_type=ldap_type,
                use_ssl=use_ssl,
                use_tls=use_tls,
                timeout=timeout,
            )
        
        # 设置 AD 特定的默认值
        if self.config.ldap_type == LDAPType.ACTIVE_DIRECTORY:
            if self.config.user_search_filter == "(uid={username})":
                self.config.user_search_filter = "(sAMAccountName={username})"
            if "username" in self.config.attributes_mapping:
                if self.config.attributes_mapping["username"] == "uid":
                    self.config.attributes_mapping["username"] = "sAMAccountName"
    
    def _create_server(self) -> "Server":
        """创建 LDAP 服务器对象"""
        return Server(
            self.config.server,
            use_ssl=self.config.use_ssl,
            get_info=ALL,
            connect_timeout=self.config.timeout,
        )
    
    def _create_connection(
        self,
        user_dn: str = None,
        password: str = None,
        auto_bind: bool = True,
    ) -> "Connection":
        """创建 LDAP 连接"""
        server = self._create_server()
        
        # 使用提供的凭证或管理员凭证
        dn = user_dn or self.config.bind_dn
        pwd = password or self.config.bind_password
        
        # AD 使用 NTLM 认证
        authentication = None
        if self.config.ldap_type == LDAPType.ACTIVE_DIRECTORY and user_dn:
            # AD 可以使用 UPN (user@domain) 或 DOMAIN\user 格式
            if "\\" not in user_dn and "@" not in user_dn:
                # 使用 DN 格式，保持简单绑定
                pass
            else:
                # 使用 NTLM
                authentication = NTLM
        
        conn = Connection(
            server,
            user=dn,
            password=pwd,
            authentication=authentication,
            auto_bind=auto_bind,
            raise_exceptions=True,
        )
        
        # STARTTLS
        if self.config.use_tls and not self.config.use_ssl:
            conn.start_tls()
        
        return conn
    
    def authenticate(
        self,
        username: str,
        password: str,
    ) -> tuple:
        """验证用户凭证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            tuple: (success, user_info_or_error)
        """
        try:
            # 首先查找用户 DN
            user_dn = self._find_user_dn(username)
            if not user_dn:
                return False, "User not found"
            
            # 尝试绑定
            try:
                conn = self._create_connection(user_dn, password)
                conn.unbind()
            except LDAPBindError:
                return False, "Invalid credentials"
            
            # 获取用户信息
            user = self.get_user(username)
            if user:
                return True, user
            
            return True, LDAPUser(dn=user_dn, username=username)
            
        except LDAPException as e:
            return False, f"LDAP error: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def _find_user_dn(self, username: str) -> Optional[str]:
        """查找用户 DN"""
        # 如果配置了 DN 模板，直接使用
        if self.config.user_dn_template:
            return self.config.user_dn_template.format(username=username)
        
        # 搜索用户
        try:
            conn = self._create_connection()
            
            search_base = self.config.user_search_base or self.config.base_dn
            search_filter = self.config.user_search_filter.format(username=username)
            
            conn.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["distinguishedName", "dn"],
            )
            
            if conn.entries:
                entry = conn.entries[0]
                return str(entry.entry_dn)
            
            conn.unbind()
            return None
            
        except LDAPException:
            return None
    
    def get_user(self, username: str) -> Optional[LDAPUser]:
        """获取用户信息
        
        Args:
            username: 用户名
            
        Returns:
            LDAPUser: 用户信息对象
        """
        try:
            conn = self._create_connection()
            
            search_base = self.config.user_search_base or self.config.base_dn
            search_filter = self.config.user_search_filter.format(username=username)
            
            # 获取所有配置的属性
            attributes = list(self.config.attributes_mapping.values())
            attributes.append("memberOf")  # 组成员关系
            
            conn.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes,
            )
            
            if not conn.entries:
                conn.unbind()
                return None
            
            entry = conn.entries[0]
            
            # 解析属性
            user = LDAPUser(
                dn=str(entry.entry_dn),
                username=username,
                raw_attributes=dict(entry.entry_attributes_as_dict),
            )
            
            # 映射属性
            mapping = self.config.attributes_mapping
            for field_name, ldap_attr in mapping.items():
                if hasattr(entry, ldap_attr):
                    value = getattr(entry, ldap_attr).value
                    if hasattr(user, field_name):
                        setattr(user, field_name, value)
            
            # 解析组
            if hasattr(entry, "memberOf"):
                member_of = entry.memberOf.values
                if member_of:
                    user.groups = self._parse_groups(member_of)
            
            conn.unbind()
            return user
            
        except LDAPException as e:
            return None
    
    def get_user_groups(self, username: str) -> List[str]:
        """获取用户所属的组
        
        Args:
            username: 用户名
            
        Returns:
            List[str]: 组名列表
        """
        user = self.get_user(username)
        if user:
            return user.groups
        return []
    
    def _parse_groups(self, member_of: List[str]) -> List[str]:
        """从 memberOf 属性解析组名"""
        groups = []
        for dn in member_of:
            # 从 DN 中提取 CN
            # 例如: CN=Developers,OU=Groups,DC=example,DC=com -> Developers
            parts = dn.split(",")
            for part in parts:
                if part.upper().startswith("CN="):
                    groups.append(part[3:])
                    break
        return groups
    
    def search_users(
        self,
        filter_str: str,
        attributes: List[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """搜索用户
        
        Args:
            filter_str: LDAP 搜索过滤器
            attributes: 要返回的属性列表
            limit: 最大返回数量
            
        Returns:
            List[Dict]: 用户列表
        """
        try:
            conn = self._create_connection()
            
            search_base = self.config.user_search_base or self.config.base_dn
            attrs = attributes or list(self.config.attributes_mapping.values())
            
            conn.search(
                search_base=search_base,
                search_filter=filter_str,
                search_scope=SUBTREE,
                attributes=attrs,
                size_limit=limit,
            )
            
            users = []
            for entry in conn.entries:
                user_dict = {
                    "dn": str(entry.entry_dn),
                }
                user_dict.update(entry.entry_attributes_as_dict)
                users.append(user_dict)
            
            conn.unbind()
            return users
            
        except LDAPException:
            return []
    
    def test_connection(self) -> tuple:
        """测试 LDAP 连接
        
        Returns:
            tuple: (success, message)
        """
        try:
            conn = self._create_connection()
            server_info = conn.server.info
            conn.unbind()
            return True, f"Connected to {self.config.server}"
        except LDAPException as e:
            return False, f"Connection failed: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"


class LDAPAuthProvider(AuthProvider):
    """LDAP 认证提供者
    
    实现 AuthProvider 接口，用于统一认证管理。
    
    使用示例:
        ldap_manager = LDAPManager(
            server="ldap://ldap.example.com:389",
            base_dn="dc=example,dc=com",
        )
        
        provider = LDAPAuthProvider(ldap_manager)
        
        result = provider.authenticate({
            "username": "john",
            "password": "secret",
        })
    """
    
    def __init__(
        self,
        ldap_manager: LDAPManager,
        role_mapping: Dict[str, List[str]] = None,
        user_sync_callback: Callable[[LDAPUser], Any] = None,
    ):
        """
        Args:
            ldap_manager: LDAP 管理器
            role_mapping: LDAP 组到角色的映射
            user_sync_callback: 用户同步回调（用于同步用户到本地数据库）
        """
        self.ldap_manager = ldap_manager
        self.role_mapping = role_mapping or {}
        self.user_sync_callback = user_sync_callback
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.LDAP
    
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证 LDAP 凭证
        
        Args:
            credentials: 凭证字典 {"username": "xxx", "password": "xxx"}
            
        Returns:
            AuthResult: 认证结果
        """
        if not isinstance(credentials, dict):
            return AuthResult.fail("Invalid credentials format", "INVALID_CREDENTIALS")
        
        username = credentials.get("username")
        password = credentials.get("password")
        
        if not username or not password:
            return AuthResult.fail("Username and password required", "MISSING_CREDENTIALS")
        
        # LDAP 认证
        success, result = self.ldap_manager.authenticate(username, password)
        
        if not success:
            return AuthResult.fail(result, "LDAP_AUTH_FAILED")
        
        ldap_user = result
        
        # 映射角色
        roles = self._map_roles(ldap_user.groups)
        
        # 同步用户（如果配置了回调）
        local_user_id = None
        if self.user_sync_callback:
            local_user = self.user_sync_callback(ldap_user)
            if local_user:
                local_user_id = getattr(local_user, "id", None)
        
        # 构建用户身份
        identity = UserIdentity(
            user_id=local_user_id or ldap_user.username,
            username=ldap_user.username,
            email=ldap_user.email,
            roles=roles,
            groups=ldap_user.groups,
            auth_type=AuthType.LDAP,
            attributes={
                "dn": ldap_user.dn,
                "display_name": ldap_user.display_name,
                "first_name": ldap_user.first_name,
                "last_name": ldap_user.last_name,
                "department": ldap_user.department,
                "title": ldap_user.title,
            },
        )
        
        return AuthResult.ok(identity)
    
    def _map_roles(self, groups: List[str]) -> List[str]:
        """将 LDAP 组映射到角色"""
        roles = []
        for group in groups:
            if group in self.role_mapping:
                roles.extend(self.role_mapping[group])
            else:
                # 默认将组名作为角色
                roles.append(group)
        return list(set(roles))  # 去重
    
    def validate_token(self, token: str) -> AuthResult:
        """LDAP 不支持 Token 验证"""
        return AuthResult.fail("LDAP does not support token validation", "NOT_SUPPORTED")


# 便捷函数：创建常见的 LDAP 配置
def create_openldap_config(
    server: str,
    base_dn: str,
    bind_dn: str = None,
    bind_password: str = None,
    use_tls: bool = False,
) -> LDAPConfig:
    """创建 OpenLDAP 配置
    
    Args:
        server: 服务器地址
        base_dn: 基础 DN
        bind_dn: 绑定 DN
        bind_password: 绑定密码
        use_tls: 是否使用 STARTTLS
        
    Returns:
        LDAPConfig: 配置对象
    """
    return LDAPConfig(
        server=server,
        base_dn=base_dn,
        bind_dn=bind_dn,
        bind_password=bind_password,
        ldap_type=LDAPType.STANDARD,
        use_tls=use_tls,
        user_search_filter="(uid={username})",
        attributes_mapping={
            "username": "uid",
            "email": "mail",
            "display_name": "displayName",
            "first_name": "givenName",
            "last_name": "sn",
        },
    )


def create_active_directory_config(
    server: str,
    base_dn: str,
    bind_dn: str = None,
    bind_password: str = None,
    use_ssl: bool = True,
) -> LDAPConfig:
    """创建 Active Directory 配置
    
    Args:
        server: 服务器地址（建议使用 ldaps:// 协议）
        base_dn: 基础 DN
        bind_dn: 绑定 DN（可以使用 UPN 格式：admin@example.com）
        bind_password: 绑定密码
        use_ssl: 是否使用 SSL
        
    Returns:
        LDAPConfig: 配置对象
    """
    return LDAPConfig(
        server=server,
        base_dn=base_dn,
        bind_dn=bind_dn,
        bind_password=bind_password,
        ldap_type=LDAPType.ACTIVE_DIRECTORY,
        use_ssl=use_ssl,
        user_search_filter="(sAMAccountName={username})",
        attributes_mapping={
            "username": "sAMAccountName",
            "email": "mail",
            "display_name": "displayName",
            "first_name": "givenName",
            "last_name": "sn",
            "phone": "telephoneNumber",
            "department": "department",
            "title": "title",
        },
    )
