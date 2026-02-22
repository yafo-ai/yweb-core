"""登录频率限制器

基于 IP 的登录频率限制，防止暴力破解攻击。
与账户级别的 LockableMixin 配合，形成两层防护：

- **第一层（IP 限制）**：同一 IP 连续失败 N 次 → 封锁该 IP M 分钟。
  保护所有用户不受暴力破解影响，不会锁定合法用户的账户。
- **第二层（账户锁定）**：同一账户从多个 IP 累计失败 N 次 → 锁定账户。
  防御分布式攻击（攻击者换 IP 继续尝试同一账户）。

使用示例::

    # 自动集成（推荐）
    auth = setup_auth(
        app=app,
        user_model=User,
        ip_max_attempts=10,         # 同一 IP 最多失败 10 次
        ip_block_minutes=15,        # 封锁 15 分钟
        max_login_attempts=20,      # 账户级别安全网（更高阈值）
    )

    # 独立使用
    from yweb.auth import LoginRateLimiter

    limiter = LoginRateLimiter(max_attempts=10, block_minutes=15)

    if limiter.is_blocked("192.168.1.100"):
        print("IP 已被封锁")

    was_blocked, remaining = limiter.record_failure("192.168.1.100")
    print(f"剩余尝试次数: {remaining}")

    limiter.reset("192.168.1.100")  # 登录成功时重置
"""

import threading
from datetime import datetime, timedelta
from typing import Tuple

from yweb.log import get_logger

logger = get_logger("yweb.auth.rate_limiter")


class LoginRateLimiter:
    """基于 IP 的登录频率限制器
    
    线程安全的内存实现，适合单实例部署。
    多实例部署可继承此类，用 Redis 替换存储。
    
    Args:
        max_attempts: 时间窗口内最大失败次数（默认 10）
        block_minutes: 封锁时长（分钟，默认 15）
        window_minutes: 失败计数的时间窗口（分钟，默认等于 block_minutes）
    """
    
    def __init__(
        self,
        max_attempts: int = 10,
        block_minutes: int = 15,
        window_minutes: int = None,
    ):
        self.max_attempts = max_attempts
        self.block_minutes = block_minutes
        self.window_minutes = window_minutes or block_minutes
        
        # ip -> {"count": int, "window_start": datetime}
        self._attempts: dict = {}
        # ip -> blocked_until (datetime)
        self._blocked: dict = {}
        self._lock = threading.Lock()
    
    def is_blocked(self, ip: str) -> bool:
        """检查 IP 是否被封锁
        
        Args:
            ip: 客户端 IP 地址
            
        Returns:
            True 表示该 IP 已被封锁
        """
        with self._lock:
            blocked_until = self._blocked.get(ip)
            if blocked_until is None:
                return False
            
            if datetime.now() >= blocked_until:
                # 封锁已过期，自动解除
                del self._blocked[ip]
                self._attempts.pop(ip, None)
                return False
            
            return True
    
    def get_block_remaining_seconds(self, ip: str) -> int:
        """获取 IP 封锁剩余秒数
        
        Args:
            ip: 客户端 IP 地址
            
        Returns:
            剩余秒数，未封锁返回 0
        """
        with self._lock:
            blocked_until = self._blocked.get(ip)
            if blocked_until is None:
                return 0
            
            remaining = (blocked_until - datetime.now()).total_seconds()
            return max(0, int(remaining))
    
    def get_remaining_attempts(self, ip: str) -> int:
        """获取剩余尝试次数
        
        Args:
            ip: 客户端 IP 地址
            
        Returns:
            剩余尝试次数
        """
        with self._lock:
            if ip in self._blocked:
                return 0
            
            entry = self._attempts.get(ip)
            if entry is None:
                return self.max_attempts
            
            # 检查时间窗口是否过期
            if datetime.now() - entry["window_start"] > timedelta(minutes=self.window_minutes):
                return self.max_attempts
            
            return max(0, self.max_attempts - entry["count"])
    
    def record_failure(self, ip: str) -> Tuple[bool, int]:
        """记录登录失败
        
        Args:
            ip: 客户端 IP 地址
            
        Returns:
            (是否触发封锁, 剩余尝试次数)
        """
        with self._lock:
            now = datetime.now()
            
            # 已经被封锁
            if ip in self._blocked:
                if now < self._blocked[ip]:
                    return True, 0
                else:
                    del self._blocked[ip]
            
            entry = self._attempts.get(ip)
            
            # 新 IP 或时间窗口已过期 → 重新开始计数
            if entry is None or (now - entry["window_start"]) > timedelta(minutes=self.window_minutes):
                self._attempts[ip] = {"count": 1, "window_start": now}
                return False, self.max_attempts - 1
            
            # 累加失败次数
            entry["count"] += 1
            remaining = self.max_attempts - entry["count"]
            
            # 达到阈值 → 封锁 IP
            if remaining <= 0:
                self._blocked[ip] = now + timedelta(minutes=self.block_minutes)
                logger.warning(
                    f"IP 已被封锁: {ip}, "
                    f"失败{entry['count']}次, 封锁{self.block_minutes}分钟"
                )
                return True, 0
            
            return False, remaining
    
    def reset(self, ip: str) -> None:
        """登录成功时重置 IP 的失败计数
        
        Args:
            ip: 客户端 IP 地址
        """
        with self._lock:
            self._attempts.pop(ip, None)
            # 注意：不清除 _blocked，已封锁的 IP 需要等过期
    
    def unblock(self, ip: str) -> bool:
        """手动解除 IP 封锁（管理员操作）
        
        Args:
            ip: 客户端 IP 地址
            
        Returns:
            True 表示成功解除
        """
        with self._lock:
            was_blocked = ip in self._blocked
            self._blocked.pop(ip, None)
            self._attempts.pop(ip, None)
            if was_blocked:
                logger.info(f"IP 封锁已手动解除: {ip}")
            return was_blocked
    
    def get_blocked_ips(self) -> dict:
        """获取当前所有被封锁的 IP（管理员查看）
        
        Returns:
            {ip: blocked_until} 字典
        """
        with self._lock:
            now = datetime.now()
            # 清理已过期的
            expired = [ip for ip, until in self._blocked.items() if now >= until]
            for ip in expired:
                del self._blocked[ip]
                self._attempts.pop(ip, None)
            
            return dict(self._blocked)
    
    def cleanup(self) -> int:
        """清理过期的记录（可定期调用）
        
        Returns:
            清理的记录数
        """
        with self._lock:
            now = datetime.now()
            cleaned = 0
            
            # 清理过期的封锁
            expired_blocked = [ip for ip, until in self._blocked.items() if now >= until]
            for ip in expired_blocked:
                del self._blocked[ip]
                cleaned += 1
            
            # 清理过期的计数窗口
            expired_attempts = [
                ip for ip, entry in self._attempts.items()
                if (now - entry["window_start"]) > timedelta(minutes=self.window_minutes)
                and ip not in self._blocked
            ]
            for ip in expired_attempts:
                del self._attempts[ip]
                cleaned += 1
            
            return cleaned
