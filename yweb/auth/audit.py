"""登录审计模块

提供登录审计服务、枚举和数据类。
抽象模型 AbstractLoginRecord 已移至 models.py。

使用示例:
    from yweb.auth import AbstractLoginRecord, LoginAuditService
    
    class LoginRecord(AbstractLoginRecord):
        __tablename__ = "login_record"
    
    audit_service = LoginAuditService(LoginRecord)
    audit_service.record_login(user_id=1, username="john", ip_address="192.168.1.1")
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any, Type, TypeVar
from dataclasses import dataclass
from enum import Enum

from .models import AbstractLoginRecord


class LoginStatus(str, Enum):
    """登录状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    LOCKED = "locked"  # 账户被锁定
    DISABLED = "disabled"  # 账户被禁用
    EXPIRED = "expired"  # 密码过期
    MFA_REQUIRED = "mfa_required"  # 需要 MFA 验证
    MFA_FAILED = "mfa_failed"  # MFA 验证失败


class LoginFailureReason(str, Enum):
    """登录失败原因枚举"""
    INVALID_USERNAME = "invalid_username"
    INVALID_PASSWORD = "invalid_password"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_DISABLED = "account_disabled"
    PASSWORD_EXPIRED = "password_expired"
    MFA_FAILED = "mfa_failed"
    MFA_TIMEOUT = "mfa_timeout"
    IP_BLOCKED = "ip_blocked"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    SESSION_EXPIRED = "session_expired"
    TOKEN_INVALID = "token_invalid"
    UNKNOWN = "unknown"


# 类型变量
LoginRecordType = TypeVar("LoginRecordType", bound=AbstractLoginRecord)


@dataclass
class LoginAttempt:
    """登录尝试数据类
    
    用于传递登录尝试信息。
    """
    username: str
    ip_address: str
    user_agent: Optional[str] = None
    user_id: Optional[int] = None
    status: str = "success"
    failure_reason: Optional[str] = None
    location: Optional[str] = None
    device_info: Optional[str] = None


class LoginAuditService:
    """登录审计服务
    
    提供登录记录的创建、查询和统计功能。
    
    使用示例:
        audit_service = LoginAuditService(LoginRecord)
        
        # 记录成功登录
        audit_service.record_login(
            user_id=1,
            username="john",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0...",
            status="success"
        )
        
        # 记录失败登录
        audit_service.record_login(
            username="john",
            ip_address="192.168.1.1",
            status="failed",
            failure_reason="invalid_password"
        )
    """
    
    def __init__(self, record_model: Type[LoginRecordType]):
        """
        Args:
            record_model: 登录记录模型类（继承自 AbstractLoginRecord）
        """
        self.record_model = record_model
    
    def record_login(
        self,
        username: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        user_id: Optional[int] = None,
        status: str = "success",
        failure_reason: Optional[str] = None,
        location: Optional[str] = None,
        device_info: Optional[str] = None,
        commit: bool = True,
    ) -> LoginRecordType:
        """记录登录尝试
        
        Args:
            username: 用户名
            ip_address: IP 地址
            user_agent: 用户代理
            user_id: 用户 ID（成功登录时）
            status: 登录状态
            failure_reason: 失败原因
            location: 地理位置
            device_info: 设备信息
            commit: 是否立即提交
            
        Returns:
            登录记录对象
        """
        record = self.record_model(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            failure_reason=failure_reason,
            location=location,
            device_info=device_info,
            login_at=datetime.now(timezone.utc),
        )
        
        # 使用 BaseModel 的 add 方法
        if hasattr(record, 'add'):
            record.add(commit)
        
        return record
    
    def record_success(
        self,
        user_id: int,
        username: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        **kwargs
    ) -> LoginRecordType:
        """记录成功登录（便捷方法）"""
        return self.record_login(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            status=LoginStatus.SUCCESS.value,
            **kwargs
        )
    
    def record_failure(
        self,
        username: str,
        ip_address: str,
        failure_reason: str,
        user_agent: Optional[str] = None,
        user_id: Optional[int] = None,
        **kwargs
    ) -> LoginRecordType:
        """记录失败登录（便捷方法）"""
        return self.record_login(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            status=LoginStatus.FAILED.value,
            failure_reason=failure_reason,
            **kwargs
        )
    
    def get_user_login_history(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[LoginRecordType]:
        """获取用户登录历史
        
        Args:
            user_id: 用户 ID
            limit: 返回数量
            offset: 偏移量
            status: 过滤状态
            
        Returns:
            登录记录列表
        """
        query = self.record_model.query.filter(
            self.record_model.user_id == user_id
        )
        
        if status:
            query = query.filter(self.record_model.status == status)
        
        return query.order_by(
            self.record_model.login_at.desc()
        ).offset(offset).limit(limit).all()
    
    def get_recent_failures(
        self,
        username: str,
        minutes: int = 30,
        ip_address: Optional[str] = None,
    ) -> int:
        """获取最近的失败登录次数
        
        用于实现登录限制。
        
        Args:
            username: 用户名
            minutes: 时间范围（分钟）
            ip_address: IP 地址（可选，限制特定 IP）
            
        Returns:
            失败次数
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        
        query = self.record_model.query.filter(
            self.record_model.username == username,
            self.record_model.status == LoginStatus.FAILED.value,
            self.record_model.login_at >= since,
        )
        
        if ip_address:
            query = query.filter(self.record_model.ip_address == ip_address)
        
        return query.count()
    
    def get_ip_login_history(
        self,
        ip_address: str,
        limit: int = 20,
        hours: int = 24,
    ) -> List[LoginRecordType]:
        """获取 IP 的登录历史
        
        用于检测异常登录。
        
        Args:
            ip_address: IP 地址
            limit: 返回数量
            hours: 时间范围（小时）
            
        Returns:
            登录记录列表
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        return self.record_model.query.filter(
            self.record_model.ip_address == ip_address,
            self.record_model.login_at >= since,
        ).order_by(
            self.record_model.login_at.desc()
        ).limit(limit).all()
    
    def get_last_successful_login(
        self,
        user_id: int
    ) -> Optional[LoginRecordType]:
        """获取用户最后一次成功登录记录"""
        return self.record_model.query.filter(
            self.record_model.user_id == user_id,
            self.record_model.status == LoginStatus.SUCCESS.value,
        ).order_by(
            self.record_model.login_at.desc()
        ).first()
    
    def count_logins_by_status(
        self,
        user_id: Optional[int] = None,
        days: int = 30,
    ) -> dict:
        """统计各状态的登录次数
        
        Args:
            user_id: 用户 ID（可选）
            days: 时间范围（天）
            
        Returns:
            {status: count} 字典
        """
        from sqlalchemy import func
        
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = self.record_model.query.filter(
            self.record_model.login_at >= since
        )
        
        if user_id:
            query = query.filter(self.record_model.user_id == user_id)
        
        # 分组统计
        results = query.with_entities(
            self.record_model.status,
            func.count(self.record_model.id)
        ).group_by(self.record_model.status).all()
        
        return {status: count for status, count in results}
    
    def cleanup_old_records(
        self,
        days: int = 90,
        keep_failures: bool = True,
    ) -> int:
        """清理旧的登录记录
        
        Args:
            days: 保留天数
            keep_failures: 是否保留失败记录
            
        Returns:
            删除的数量
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = self.record_model.query.filter(
            self.record_model.login_at < cutoff
        )
        
        if keep_failures:
            query = query.filter(
                self.record_model.status == LoginStatus.SUCCESS.value
            )
        
        count = query.count()
        query.delete()
        
        return count
