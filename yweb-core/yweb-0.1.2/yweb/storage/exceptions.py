# -*- coding: utf-8 -*-
"""
存储模块异常定义

异常层级:
    StorageError (基类)
    ├── StorageConfigError      - 配置错误
    ├── StorageNotFoundError    - 存储后端未找到
    ├── StorageQuotaExceeded    - 存储配额超限
    ├── InvalidFileError        - 无效的文件
    │   ├── InvalidFileType     - 无效的文件类型
    │   ├── FileTooLarge        - 文件过大
    │   └── FileTooSmall        - 文件过小
    ├── FileValidationError     - 文件验证失败
    ├── SecureURLError          - 安全URL相关错误
    │   ├── TokenExpired        - Token已过期
    │   ├── TokenInvalid        - Token无效
    │   └── SignatureInvalid    - 签名无效
    └── MultipartUploadError    - 分片上传错误
"""

from typing import Optional, List


class StorageError(Exception):
    """存储操作错误基类
    
    所有存储相关异常的基类，便于统一捕获。
    
    Attributes:
        message: 错误消息
        code: 错误码（可选）
        details: 详细信息（可选）
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """转换为字典（用于API响应）"""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ==================== 配置相关异常 ====================

class StorageConfigError(StorageError):
    """存储配置错误
    
    配置验证失败、缺少必要配置等。
    """
    pass


class StorageNotFoundError(StorageError):
    """存储后端未找到
    
    请求的存储后端未注册。
    """
    
    def __init__(self, backend_name: str):
        super().__init__(
            message=f"存储后端未注册: {backend_name}",
            code="STORAGE_NOT_FOUND",
            details={"backend": backend_name},
        )


# ==================== 配额相关异常 ====================

class StorageQuotaExceeded(StorageError):
    """存储配额超限
    
    存储空间不足、文件数量超限等。
    """
    
    def __init__(
        self,
        message: str = "存储配额超限",
        current: Optional[int] = None,
        limit: Optional[int] = None,
    ):
        details = {}
        if current is not None:
            details["current"] = current
        if limit is not None:
            details["limit"] = limit
        
        super().__init__(
            message=message,
            code="QUOTA_EXCEEDED",
            details=details,
        )


# ==================== 文件验证相关异常 ====================

class InvalidFileError(StorageError):
    """无效的文件
    
    文件不符合要求的基类异常。
    """
    pass


class InvalidFileType(InvalidFileError):
    """无效的文件类型
    
    文件扩展名或MIME类型不被允许。
    """
    
    def __init__(
        self,
        message: str = "无效的文件类型",
        actual_type: Optional[str] = None,
        allowed_types: Optional[List[str]] = None,
    ):
        details = {}
        if actual_type:
            details["actual_type"] = actual_type
        if allowed_types:
            details["allowed_types"] = allowed_types
        
        super().__init__(
            message=message,
            code="INVALID_FILE_TYPE",
            details=details,
        )


class FileTooLarge(InvalidFileError):
    """文件过大"""
    
    def __init__(
        self,
        actual_size: int,
        max_size: int,
    ):
        super().__init__(
            message=f"文件大小 {actual_size} 超过限制 {max_size}",
            code="FILE_TOO_LARGE",
            details={
                "actual_size": actual_size,
                "max_size": max_size,
            },
        )


class FileTooSmall(InvalidFileError):
    """文件过小"""
    
    def __init__(
        self,
        actual_size: int,
        min_size: int,
    ):
        super().__init__(
            message=f"文件大小 {actual_size} 小于最小要求 {min_size}",
            code="FILE_TOO_SMALL",
            details={
                "actual_size": actual_size,
                "min_size": min_size,
            },
        )


class FileValidationError(StorageError):
    """文件验证失败
    
    文件内容验证失败，可能包含多个错误。
    """
    
    def __init__(
        self,
        errors: List[str],
        warnings: Optional[List[str]] = None,
    ):
        message = "; ".join(errors) if errors else "文件验证失败"
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            details={
                "errors": errors,
                "warnings": warnings or [],
            },
        )
        self.errors = errors
        self.warnings = warnings or []


# ==================== 安全URL相关异常 ====================

class SecureURLError(StorageError):
    """安全URL相关错误基类"""
    pass


class TokenExpired(SecureURLError):
    """Token已过期"""
    
    def __init__(self, token: Optional[str] = None):
        super().__init__(
            message="访问令牌已过期",
            code="TOKEN_EXPIRED",
            details={"token": token[:8] + "..." if token else None},
        )


class TokenInvalid(SecureURLError):
    """Token无效"""
    
    def __init__(self, reason: str = "令牌无效或不存在"):
        super().__init__(
            message=reason,
            code="TOKEN_INVALID",
        )


class SignatureInvalid(SecureURLError):
    """签名无效"""
    
    def __init__(self):
        super().__init__(
            message="URL签名验证失败",
            code="SIGNATURE_INVALID",
        )


# ==================== 分片上传相关异常 ====================

class MultipartUploadError(StorageError):
    """分片上传错误基类"""
    pass


class UploadNotFound(MultipartUploadError):
    """上传任务不存在"""
    
    def __init__(self, upload_id: str):
        super().__init__(
            message=f"上传任务不存在: {upload_id}",
            code="UPLOAD_NOT_FOUND",
            details={"upload_id": upload_id},
        )


class UploadExpired(MultipartUploadError):
    """上传任务已过期"""
    
    def __init__(self, upload_id: str):
        super().__init__(
            message=f"上传任务已过期: {upload_id}",
            code="UPLOAD_EXPIRED",
            details={"upload_id": upload_id},
        )


class PartNumberInvalid(MultipartUploadError):
    """分片序号无效"""
    
    def __init__(self, part_number: int):
        super().__init__(
            message=f"分片序号必须在 1-10000 之间，当前: {part_number}",
            code="PART_NUMBER_INVALID",
            details={"part_number": part_number},
        )


class PartVerificationFailed(MultipartUploadError):
    """分片验证失败"""
    
    def __init__(self, part_number: int, expected_etag: str, actual_etag: str):
        super().__init__(
            message=f"分片 {part_number} 验证失败",
            code="PART_VERIFICATION_FAILED",
            details={
                "part_number": part_number,
                "expected_etag": expected_etag,
                "actual_etag": actual_etag,
            },
        )


# ==================== 便捷导出 ====================

__all__ = [
    # 基类
    "StorageError",
    # 配置
    "StorageConfigError",
    "StorageNotFoundError",
    # 配额
    "StorageQuotaExceeded",
    # 文件验证
    "InvalidFileError",
    "InvalidFileType",
    "FileTooLarge",
    "FileTooSmall",
    "FileValidationError",
    # 安全URL
    "SecureURLError",
    "TokenExpired",
    "TokenInvalid",
    "SignatureInvalid",
    # 分片上传
    "MultipartUploadError",
    "UploadNotFound",
    "UploadExpired",
    "PartNumberInvalid",
    "PartVerificationFailed",
]
