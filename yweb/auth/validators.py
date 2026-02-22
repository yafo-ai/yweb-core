"""认证相关验证器

提供认证场景专用的验证工具：
- PasswordStrength: 密码强度等级枚举
- PasswordValidator: 密码强度验证（与 PasswordHelper 哈希互补）
- UsernameValidator: 用户名格式验证

邮箱和手机号验证请使用 yweb.validators 模块::

    # DTO 层（Pydantic 声明式）
    from yweb.validators import Phone, Email, Typed
    class UserCreate(BaseModel):
        phone: Annotated[str, Phone]
        email: Typed.Email

    # Service 层（命令式）
    from yweb.validators import is_valid_phone, is_valid_email
    if is_valid_email(email):
        ...

使用示例:

    密码验证（强度等级 + 长度分离）::
    
        from yweb.auth.validators import PasswordValidator, PasswordStrength
        
        # 使用默认规则（STRONG: 大小写 + 数字 + 特殊字符，长度 8-128）
        PasswordValidator.validate("MyP@ss123")  # True
        
        # 用预设等级快速创建
        v = PasswordValidator.of(PasswordStrength.BASIC, min_length=6)
        v.validate_instance("abc123")  # True（字母+数字，6位）
        
        # 修改全局默认等级
        PasswordValidator.configure(strength=PasswordStrength.MEDIUM, min_length=6)
        PasswordValidator.validate("Abc123")  # True（大小写+数字，6位）
    
    用户名验证::
    
        from yweb.auth.validators import UsernameValidator
        
        UsernameValidator.validate("admin")   # True
        UsernameValidator.validate("管理员")   # True
"""

import re
from enum import Enum
from typing import List, Optional


class ValidationError(ValueError):
    """验证失败异常
    
    Attributes:
        errors: 错误信息列表
    """
    
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


class PasswordStrength(str, Enum):
    """密码强度等级
    
    三个等级，字符要求逐级递增，长度单独配置::
    
        BASIC  = 字母 + 数字
        MEDIUM = 大写字母 + 小写字母 + 数字
        STRONG = 大写字母 + 小写字母 + 数字 + 特殊字符
    """
    BASIC = "basic"
    """基础：字母 + 数字"""
    
    MEDIUM = "medium"
    """中等：大写字母 + 小写字母 + 数字"""
    
    STRONG = "strong"
    """强：大写字母 + 小写字母 + 数字 + 特殊字符"""


# 每个等级对应的字符要求
_STRENGTH_RULES = {
    PasswordStrength.BASIC: {
        "require_letter": True,
        "require_upper": False,
        "require_lower": False,
        "require_digit": True,
        "require_special": False,
    },
    PasswordStrength.MEDIUM: {
        "require_letter": False,
        "require_upper": True,
        "require_lower": True,
        "require_digit": True,
        "require_special": False,
    },
    PasswordStrength.STRONG: {
        "require_letter": False,
        "require_upper": True,
        "require_lower": True,
        "require_digit": True,
        "require_special": True,
    },
}


class PasswordValidator:
    """密码强度验证器
    
    采用「强度等级 + 长度」两个维度组合，简单直观。
    与 PasswordHelper（负责哈希/验证）互补，本类只负责检查密码格式和强度。
    
    强度等级:
        - BASIC:  字母 + 数字
        - MEDIUM: 大写字母 + 小写字母 + 数字
        - STRONG: 大写字母 + 小写字母 + 数字 + 特殊字符
    
    长度:
        - min_length / max_length 独立于强度等级，自由组合
    
    默认规则: STRONG + 长度 8-128
    
    使用示例:
        # 类方法 — 使用全局默认规则
        PasswordValidator.validate("MyP@ss123")       # True
        PasswordValidator.validate_or_raise("weak")   # 抛出 ValidationError
        
        # 工厂方法 — 指定等级 + 长度
        v = PasswordValidator.of(PasswordStrength.BASIC, min_length=6)
        v.validate_instance("abc123")                 # True
        
        v = PasswordValidator.of(PasswordStrength.MEDIUM, min_length=8)
        v.validate_instance("Abcdefg1")               # True
        
        # 构造函数 — 完全自定义（高级用法）
        v = PasswordValidator(
            min_length=10,
            require_upper=True,
            require_digit=True,
            require_special=False,
        )
        
        # 修改全局默认
        PasswordValidator.configure(strength=PasswordStrength.BASIC, min_length=6)
    """
    
    # 全局默认
    _default_strength: PasswordStrength = PasswordStrength.STRONG
    _default_min_length: int = 8
    _default_max_length: int = 128
    
    def __init__(
        self,
        min_length: int = 8,
        max_length: int = 128,
        require_letter: bool = False,
        require_upper: bool = False,
        require_lower: bool = False,
        require_digit: bool = False,
        require_special: bool = False,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_letter = require_letter
        self.require_upper = require_upper
        self.require_lower = require_lower
        self.require_digit = require_digit
        self.require_special = require_special
    
    @classmethod
    def of(
        cls,
        strength: PasswordStrength,
        min_length: int = 8,
        max_length: int = 128,
    ) -> "PasswordValidator":
        """通过强度等级创建验证器（推荐）
        
        Args:
            strength: 密码强度等级
            min_length: 最小长度
            max_length: 最大长度
            
        Returns:
            PasswordValidator 实例
        
        使用示例:
            v = PasswordValidator.of(PasswordStrength.BASIC, min_length=6)
            v.validate_instance("abc123")  # True
        """
        rules = _STRENGTH_RULES[strength]
        return cls(min_length=min_length, max_length=max_length, **rules)
    
    def get_errors(self, password: str) -> List[str]:
        """获取密码不满足的所有规则
        
        Args:
            password: 待验证的密码
            
        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []
        
        if len(password) < self.min_length:
            errors.append(f"密码长度不能少于 {self.min_length} 个字符")
        if len(password) > self.max_length:
            errors.append(f"密码长度不能超过 {self.max_length} 个字符")
        if self.require_letter and not re.search(r"[a-zA-Z]", password):
            errors.append("密码必须包含字母")
        if self.require_upper and not re.search(r"[A-Z]", password):
            errors.append("密码必须包含大写字母")
        if self.require_lower and not re.search(r"[a-z]", password):
            errors.append("密码必须包含小写字母")
        if self.require_digit and not re.search(r"[0-9]", password):
            errors.append("密码必须包含数字")
        if self.require_special and not re.search(
            r"[!@#$%^&*(),.?;:{}|<>+\-_=\[\]\\/'\"~`]", password
        ):
            errors.append("密码必须包含特殊字符")
        
        return errors
    
    @classmethod
    def _default_instance(cls) -> "PasswordValidator":
        """根据全局默认配置创建实例"""
        return cls.of(
            strength=cls._default_strength,
            min_length=cls._default_min_length,
            max_length=cls._default_max_length,
        )
    
    @classmethod
    def validate(cls, password: str) -> bool:
        """使用全局默认规则验证密码
        
        Args:
            password: 待验证的密码
            
        Returns:
            是否通过验证
        """
        return cls._default_instance().validate_instance(password)
    
    @classmethod
    def validate_or_raise(cls, password: str) -> None:
        """使用全局默认规则验证密码，失败抛异常
        
        Args:
            password: 待验证的密码
            
        Raises:
            ValidationError: 验证失败
        """
        cls._default_instance().validate_instance_or_raise(password)
    
    def validate_instance(self, password: str) -> bool:
        """使用实例规则验证密码
        
        Args:
            password: 待验证的密码
            
        Returns:
            是否通过验证
        """
        return len(self.get_errors(password)) == 0
    
    def validate_instance_or_raise(self, password: str) -> None:
        """使用实例规则验证密码，失败抛异常
        
        Args:
            password: 待验证的密码
            
        Raises:
            ValidationError: 验证失败
        """
        errors = self.get_errors(password)
        if errors:
            raise ValidationError(
                f"密码不满足要求: {'; '.join(errors)}",
                errors=errors,
            )
    
    @classmethod
    def configure(
        cls,
        strength: Optional[PasswordStrength] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> None:
        """修改全局默认规则（影响类方法 validate / validate_or_raise）
        
        Args:
            strength: 密码强度等级
            min_length: 最小长度
            max_length: 最大长度
        
        使用示例:
            # 降低为基础强度，最少 6 位
            PasswordValidator.configure(
                strength=PasswordStrength.BASIC,
                min_length=6,
            )
        """
        if strength is not None:
            cls._default_strength = strength
        if min_length is not None:
            cls._default_min_length = min_length
        if max_length is not None:
            cls._default_max_length = max_length


class UsernameValidator:
    """用户名格式验证器
    
    默认规则:
        - 长度 1-20 个字符
        - 允许中文、英文字母、数字、下划线
    
    使用示例:
        UsernameValidator.validate("admin")       # True
        UsernameValidator.validate("管理员")       # True
        UsernameValidator.validate("user@name")   # False
        
        # 自定义规则
        v = UsernameValidator(min_length=3, allow_chinese=False)
        v.validate_instance("ab")  # False (太短)
    """
    
    _default_min_length: int = 1
    _default_max_length: int = 20
    _default_allow_chinese: bool = True
    
    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 20,
        allow_chinese: bool = True,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.allow_chinese = allow_chinese
        
        # 构建正则
        if allow_chinese:
            self._pattern = re.compile(r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$")
        else:
            self._pattern = re.compile(r"^[a-zA-Z0-9_]+$")
    
    def get_errors(self, username: str) -> List[str]:
        """获取用户名不满足的所有规则
        
        Args:
            username: 待验证的用户名
            
        Returns:
            错误信息列表
        """
        errors = []
        
        if not username:
            errors.append("用户名不能为空")
            return errors
        
        if len(username) < self.min_length:
            errors.append(f"用户名长度不能少于 {self.min_length} 个字符")
        if len(username) > self.max_length:
            errors.append(f"用户名长度不能超过 {self.max_length} 个字符")
        if not self._pattern.match(username):
            if self.allow_chinese:
                errors.append("用户名只能包含中文、字母、数字和下划线")
            else:
                errors.append("用户名只能包含字母、数字和下划线")
        
        return errors
    
    @classmethod
    def validate(cls, username: str) -> bool:
        """使用默认规则验证用户名（类方法）
        
        Args:
            username: 待验证的用户名
            
        Returns:
            是否通过验证
        """
        instance = cls(
            min_length=cls._default_min_length,
            max_length=cls._default_max_length,
            allow_chinese=cls._default_allow_chinese,
        )
        return len(instance.get_errors(username)) == 0
    
    @classmethod
    def validate_or_raise(cls, username: str) -> None:
        """使用默认规则验证用户名，失败抛异常（类方法）
        
        Args:
            username: 待验证的用户名
            
        Raises:
            ValidationError: 验证失败
        """
        instance = cls(
            min_length=cls._default_min_length,
            max_length=cls._default_max_length,
            allow_chinese=cls._default_allow_chinese,
        )
        errors = instance.get_errors(username)
        if errors:
            raise ValidationError(
                f"用户名不满足要求: {'; '.join(errors)}",
                errors=errors,
            )
    
    def validate_instance(self, username: str) -> bool:
        """使用实例规则验证用户名"""
        return len(self.get_errors(username)) == 0
    
    def validate_instance_or_raise(self, username: str) -> None:
        """使用实例规则验证用户名，失败抛异常"""
        errors = self.get_errors(username)
        if errors:
            raise ValidationError(
                f"用户名不满足要求: {'; '.join(errors)}",
                errors=errors,
            )
    
    @classmethod
    def configure(
        cls,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        allow_chinese: Optional[bool] = None,
    ) -> None:
        """修改默认规则
        
        Args:
            min_length: 最小长度
            max_length: 最大长度
            allow_chinese: 是否允许中文
        """
        if min_length is not None:
            cls._default_min_length = min_length
        if max_length is not None:
            cls._default_max_length = max_length
        if allow_chinese is not None:
            cls._default_allow_chinese = allow_chinese


__all__ = [
    "ValidationError",
    "PasswordStrength",
    "PasswordValidator",
    "UsernameValidator",
]
