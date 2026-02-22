"""恢复码提供者

提供备用恢复码功能，用于用户无法使用主要 MFA 方式时的紧急访问。

使用示例:
    provider = RecoveryCodeProvider(
        code_count=10,
        code_length=8,
    )
    
    # 为用户生成恢复码
    setup_data = provider.setup(user_id=1)
    print(setup_data.recovery_codes)  # ['ABCD-1234', 'EFGH-5678', ...]
    
    # 使用恢复码
    result = provider.verify(user_id=1, code="ABCD-1234")
    if result.success:
        print("恢复成功，该码已失效")
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Callable, Set

from .base import MFAProvider, MFAType, MFASetupData, MFAVerifyResult


def generate_recovery_code(length: int = 8) -> str:
    """生成恢复码
    
    生成易于阅读的恢复码（大写字母和数字，排除易混淆字符）
    
    Args:
        length: 恢复码长度
        
    Returns:
        str: 恢复码（格式：XXXX-XXXX）
    """
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(chars) for _ in range(length))
    # 添加分隔符便于阅读
    mid = length // 2
    return f"{code[:mid]}-{code[mid:]}"


@dataclass
class RecoveryCodeSet:
    """恢复码集合"""
    user_id: Any
    codes: Set[str]  # 哈希后的恢复码
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    used_codes: Set[str] = field(default_factory=set)  # 已使用的码
    
    def remaining_count(self) -> int:
        """剩余可用恢复码数量"""
        return len(self.codes) - len(self.used_codes)
    
    def is_code_valid(self, code_hash: str) -> bool:
        """检查恢复码是否有效"""
        return code_hash in self.codes and code_hash not in self.used_codes
    
    def use_code(self, code_hash: str) -> bool:
        """使用恢复码"""
        if self.is_code_valid(code_hash):
            self.used_codes.add(code_hash)
            return True
        return False


class RecoveryCodeProvider(MFAProvider):
    """恢复码提供者
    
    提供备用恢复码功能，每个恢复码只能使用一次。
    
    Args:
        code_count: 生成的恢复码数量
        code_length: 每个恢复码的长度
        store: 存储回调
        getter: 获取回调
    """
    
    def __init__(
        self,
        code_count: int = 10,
        code_length: int = 8,
        store: Callable[[Any, RecoveryCodeSet], bool] = None,
        getter: Callable[[Any], Optional[RecoveryCodeSet]] = None,
    ):
        self.code_count = code_count
        self.code_length = code_length
        
        self._store = store
        self._getter = getter
        
        # 内存存储（默认）
        self._code_sets: Dict[Any, RecoveryCodeSet] = {}
    
    def set_stores(
        self,
        store: Callable[[Any, RecoveryCodeSet], bool],
        getter: Callable[[Any], Optional[RecoveryCodeSet]],
    ) -> "RecoveryCodeProvider":
        """设置存储回调"""
        self._store = store
        self._getter = getter
        return self
    
    @property
    def mfa_type(self) -> MFAType:
        return MFAType.RECOVERY
    
    def setup(self, user_id: Any, **kwargs) -> MFASetupData:
        """生成恢复码
        
        Args:
            user_id: 用户 ID
            
        Returns:
            MFASetupData: 包含恢复码列表
        """
        # 生成恢复码
        plain_codes = []
        code_hashes = set()
        
        for _ in range(self.code_count):
            code = generate_recovery_code(self.code_length)
            plain_codes.append(code)
            code_hashes.add(self._hash_code(code))
        
        # 存储哈希后的恢复码
        code_set = RecoveryCodeSet(
            user_id=user_id,
            codes=code_hashes,
        )
        self._save_codes(user_id, code_set)
        
        return MFASetupData(
            mfa_type=MFAType.RECOVERY,
            recovery_codes=plain_codes,
            extra={
                "count": self.code_count,
            },
        )
    
    def verify(
        self,
        user_id: Any,
        code: str,
        **kwargs,
    ) -> MFAVerifyResult:
        """验证恢复码
        
        Args:
            user_id: 用户 ID
            code: 恢复码
            
        Returns:
            MFAVerifyResult: 验证结果
        """
        code_set = self._get_codes(user_id)
        if not code_set:
            return MFAVerifyResult.fail("No recovery codes found")
        
        # 标准化代码格式
        normalized_code = code.upper().replace(" ", "").replace("-", "")
        # 重新添加分隔符
        mid = len(normalized_code) // 2
        normalized_code = f"{normalized_code[:mid]}-{normalized_code[mid:]}"
        
        code_hash = self._hash_code(normalized_code)
        
        if not code_set.is_code_valid(code_hash):
            remaining = code_set.remaining_count()
            return MFAVerifyResult.fail(
                "Invalid or already used recovery code",
                remaining_attempts=remaining,
            )
        
        # 使用恢复码
        code_set.use_code(code_hash)
        self._save_codes(user_id, code_set)
        
        remaining = code_set.remaining_count()
        result = MFAVerifyResult.ok(f"Recovery code accepted. {remaining} codes remaining")
        result.recovery_code_used = True
        
        return result
    
    def is_enabled(self, user_id: Any) -> bool:
        """检查用户是否有可用的恢复码"""
        code_set = self._get_codes(user_id)
        return code_set is not None and code_set.remaining_count() > 0
    
    def disable(self, user_id: Any) -> bool:
        """删除用户的所有恢复码"""
        if self._store:
            return self._store(user_id, None)
        if user_id in self._code_sets:
            del self._code_sets[user_id]
            return True
        return False
    
    def regenerate(self, user_id: Any) -> MFASetupData:
        """重新生成恢复码（作废旧的）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            MFASetupData: 新的恢复码
        """
        return self.setup(user_id)
    
    def get_remaining_count(self, user_id: Any) -> int:
        """获取剩余可用恢复码数量
        
        Args:
            user_id: 用户 ID
            
        Returns:
            int: 剩余数量
        """
        code_set = self._get_codes(user_id)
        return code_set.remaining_count() if code_set else 0
    
    def _hash_code(self, code: str) -> str:
        """计算恢复码哈希"""
        import hashlib
        return hashlib.sha256(code.encode()).hexdigest()
    
    def _save_codes(self, user_id: Any, code_set: RecoveryCodeSet) -> bool:
        """保存恢复码"""
        if self._store:
            return self._store(user_id, code_set)
        self._code_sets[user_id] = code_set
        return True
    
    def _get_codes(self, user_id: Any) -> Optional[RecoveryCodeSet]:
        """获取恢复码"""
        if self._getter:
            return self._getter(user_id)
        return self._code_sets.get(user_id)
