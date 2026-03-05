# -*- coding: utf-8 -*-
"""
文件验证模块

提供可配置的文件验证功能，包括：
- 文件大小验证
- 扩展名验证
- MIME类型验证
- 魔数验证（防止伪造扩展名）
- 图片尺寸验证
- 自定义验证器

使用示例:
    # 使用预设配置
    validator = FileValidator(preset='image')
    result = validator.validate(file_content, 'avatar.jpg')
    
    # 自定义配置
    config = FileValidationConfig(
        max_size=5*1024*1024,
        allowed_extensions={'.pdf', '.doc'},
    )
    validator = FileValidator(config=config)
"""

import logging
import mimetypes
from dataclasses import dataclass, field
from typing import Set, Optional, Callable, List, Union, BinaryIO, Dict, Any
from io import BytesIO

from .exceptions import FileValidationError, FileTooLarge, FileTooSmall, InvalidFileType

logger = logging.getLogger(__name__)


@dataclass
class FileValidationConfig:
    """文件验证配置
    
    Attributes:
        max_size: 最大文件大小（字节）
        min_size: 最小文件大小（字节）
        allowed_extensions: 允许的扩展名集合，如 {'.jpg', '.png'}
        blocked_extensions: 禁止的扩展名集合，如 {'.exe', '.sh'}
        allowed_mimes: 允许的MIME类型集合
        blocked_mimes: 禁止的MIME类型集合
        verify_magic: 是否验证文件魔数
        image_max_width: 图片最大宽度
        image_max_height: 图片最大高度
        image_max_pixels: 图片最大像素数（防止解压炸弹）
        custom_validators: 自定义验证函数列表
    
    Example:
        config = FileValidationConfig(
            max_size=10*1024*1024,  # 10MB
            allowed_extensions={'.jpg', '.png'},
            image_max_width=4096,
        )
    """
    
    # 大小限制
    max_size: Optional[int] = None
    min_size: int = 0
    
    # 类型限制
    allowed_extensions: Set[str] = field(default_factory=set)
    blocked_extensions: Set[str] = field(default_factory=set)
    allowed_mimes: Set[str] = field(default_factory=set)
    blocked_mimes: Set[str] = field(default_factory=set)
    
    # 内容验证
    verify_magic: bool = True
    
    # 图片特定验证
    image_max_width: Optional[int] = None
    image_max_height: Optional[int] = None
    image_max_pixels: Optional[int] = None
    
    # 自定义验证器
    custom_validators: List[Callable[[bytes, str, Optional[str]], Union[bool, str, None]]] = field(default_factory=list)


@dataclass
class ValidationResult:
    """验证结果
    
    Attributes:
        valid: 是否通过验证
        errors: 错误列表
        warnings: 警告列表
        size: 文件大小
        detected_mime: 检测到的MIME类型
        image_info: 图片信息（如果是图片）
    """
    valid: bool
    errors: List[str]
    warnings: List[str]
    size: int
    detected_mime: Optional[str] = None
    image_info: Optional[Dict[str, Any]] = None
    
    def raise_if_invalid(self) -> None:
        """如果验证失败则抛出异常"""
        if not self.valid:
            raise FileValidationError(self.errors, self.warnings)


# MIME类型与扩展名映射
MIME_EXTENSION_MAP: Dict[str, Set[str]] = {
    'image/jpeg': {'.jpg', '.jpeg'},
    'image/png': {'.png'},
    'image/gif': {'.gif'},
    'image/webp': {'.webp'},
    'image/bmp': {'.bmp'},
    'image/svg+xml': {'.svg'},
    'application/pdf': {'.pdf'},
    'application/msword': {'.doc'},
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'.docx'},
    'application/vnd.ms-excel': {'.xls'},
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {'.xlsx'},
    'application/vnd.ms-powerpoint': {'.ppt'},
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': {'.pptx'},
    'text/plain': {'.txt'},
    'text/html': {'.html', '.htm'},
    'text/css': {'.css'},
    'text/javascript': {'.js'},
    'application/json': {'.json'},
    'application/xml': {'.xml'},
    'application/zip': {'.zip'},
    'application/x-rar-compressed': {'.rar'},
    'application/x-7z-compressed': {'.7z'},
    'application/x-tar': {'.tar'},
    'application/gzip': {'.gz'},
    'video/mp4': {'.mp4'},
    'video/x-msvideo': {'.avi'},
    'video/quicktime': {'.mov'},
    'video/x-matroska': {'.mkv'},
    'video/webm': {'.webm'},
    'audio/mpeg': {'.mp3'},
    'audio/wav': {'.wav'},
    'audio/ogg': {'.ogg'},
}

# 图片扩展名
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}


class FileValidator:
    """文件验证器
    
    提供文件内容验证功能，支持预设配置和自定义配置。
    
    Args:
        config: 验证配置
        preset: 预设名称 ('image', 'document', 'avatar', 'video')
    
    Example:
        # 使用预设
        validator = FileValidator(preset='image')
        result = validator.validate(file_bytes, 'photo.jpg')
        if not result.valid:
            print(result.errors)
        
        # 使用自定义配置
        config = FileValidationConfig(
            max_size=5*1024*1024,
            allowed_extensions={'.pdf'},
        )
        validator = FileValidator(config=config)
    """
    
    # 预定义配置
    PRESETS: Dict[str, FileValidationConfig] = {
        'image': FileValidationConfig(
            max_size=10 * 1024 * 1024,  # 10MB
            allowed_extensions={'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'},
            allowed_mimes={'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'},
            image_max_pixels=100_000_000,  # 1亿像素
        ),
        'document': FileValidationConfig(
            max_size=50 * 1024 * 1024,  # 50MB
            allowed_extensions={'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'},
        ),
        'avatar': FileValidationConfig(
            max_size=2 * 1024 * 1024,  # 2MB
            allowed_extensions={'.jpg', '.jpeg', '.png'},
            allowed_mimes={'image/jpeg', 'image/png'},
            image_max_width=4096,
            image_max_height=4096,
        ),
        'video': FileValidationConfig(
            max_size=500 * 1024 * 1024,  # 500MB
            allowed_extensions={'.mp4', '.avi', '.mov', '.mkv', '.webm'},
        ),
        'any': FileValidationConfig(
            # 允许所有文件，仅检查大小
            max_size=100 * 1024 * 1024,  # 100MB
            verify_magic=False,
        ),
    }
    
    def __init__(
        self,
        config: Optional[FileValidationConfig] = None,
        preset: Optional[str] = None,
    ):
        if preset:
            if preset not in self.PRESETS:
                raise ValueError(f"未知的预设: {preset}，可用: {list(self.PRESETS.keys())}")
            self.config = self.PRESETS[preset]
        else:
            self.config = config or FileValidationConfig()
    
    def validate(
        self,
        content: Union[bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
    ) -> ValidationResult:
        """验证文件
        
        Args:
            content: 文件内容（字节或文件对象）
            filename: 文件名（用于扩展名验证）
            content_type: 声明的MIME类型
            
        Returns:
            ValidationResult: 验证结果
        """
        errors: List[str] = []
        warnings: List[str] = []
        detected_mime: Optional[str] = None
        image_info: Optional[Dict[str, Any]] = None
        
        # 读取内容
        if isinstance(content, bytes):
            data = content
        else:
            pos = content.tell()
            data = content.read()
            content.seek(pos)
        
        size = len(data)
        
        # 1. 大小验证
        size_errors = self._validate_size(size)
        errors.extend(size_errors)
        
        # 2. 扩展名验证
        ext = self._get_extension(filename).lower()
        ext_errors = self._validate_extension(ext)
        errors.extend(ext_errors)
        
        # 3. 声明的MIME类型验证
        if content_type:
            mime_warnings, mime_errors = self._validate_declared_mime(content_type)
            warnings.extend(mime_warnings)
            errors.extend(mime_errors)
        
        # 4. 魔数验证（检测实际类型）
        if self.config.verify_magic:
            detected_mime, magic_warnings, magic_errors = self._validate_magic(data, ext)
            warnings.extend(magic_warnings)
            errors.extend(magic_errors)
        
        # 5. 图片特定验证
        if ext in IMAGE_EXTENSIONS:
            img_errors, img_info = self._validate_image(data)
            errors.extend(img_errors)
            image_info = img_info
        
        # 6. 自定义验证器
        custom_errors = self._run_custom_validators(data, filename, content_type)
        errors.extend(custom_errors)
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            size=size,
            detected_mime=detected_mime,
            image_info=image_info,
        )
    
    def validate_or_raise(
        self,
        content: Union[bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
    ) -> ValidationResult:
        """验证文件，失败时抛出异常
        
        Args:
            content: 文件内容
            filename: 文件名
            content_type: 声明的MIME类型
            
        Returns:
            ValidationResult: 验证结果
            
        Raises:
            FileValidationError: 验证失败
        """
        result = self.validate(content, filename, content_type)
        result.raise_if_invalid()
        return result
    
    def _validate_size(self, size: int) -> List[str]:
        """验证文件大小"""
        errors = []
        
        if self.config.max_size and size > self.config.max_size:
            errors.append(
                f"文件大小 {size} 字节超过限制 {self.config.max_size} 字节"
            )
        
        if size < self.config.min_size:
            errors.append(
                f"文件大小 {size} 字节小于最小要求 {self.config.min_size} 字节"
            )
        
        return errors
    
    def _validate_extension(self, ext: str) -> List[str]:
        """验证扩展名"""
        errors = []
        
        if self.config.allowed_extensions and ext not in self.config.allowed_extensions:
            errors.append(
                f"不允许的文件扩展名: {ext}，允许: {self.config.allowed_extensions}"
            )
        
        if ext in self.config.blocked_extensions:
            errors.append(f"禁止的文件扩展名: {ext}")
        
        return errors
    
    def _validate_declared_mime(self, content_type: str) -> tuple:
        """验证声明的MIME类型"""
        warnings = []
        errors = []
        
        if self.config.allowed_mimes and content_type not in self.config.allowed_mimes:
            warnings.append(f"声明的MIME类型不在允许列表: {content_type}")
        
        if content_type in self.config.blocked_mimes:
            errors.append(f"禁止的MIME类型: {content_type}")
        
        return warnings, errors
    
    def _validate_magic(self, data: bytes, ext: str) -> tuple:
        """验证文件魔数（实际类型）"""
        warnings = []
        errors = []
        detected_mime = None
        
        try:
            # 尝试使用 python-magic
            try:
                import magic
                detected_mime = magic.from_buffer(data[:2048], mime=True)
            except ImportError:
                # 降级：使用简单的魔数检测
                detected_mime = self._detect_mime_simple(data)
            
            if detected_mime:
                # 检查扩展名与实际类型是否匹配
                if not self._mime_matches_extension(detected_mime, ext):
                    warnings.append(
                        f"文件扩展名 {ext} 与实际类型 {detected_mime} 不匹配"
                    )
                
                # 检查实际类型是否允许
                if self.config.allowed_mimes and detected_mime not in self.config.allowed_mimes:
                    errors.append(f"实际文件类型不允许: {detected_mime}")
                
                if detected_mime in self.config.blocked_mimes:
                    errors.append(f"禁止的实际文件类型: {detected_mime}")
        
        except Exception as e:
            logger.warning(f"无法检测文件类型: {e}")
            warnings.append(f"无法检测文件类型: {e}")
        
        return detected_mime, warnings, errors
    
    def _detect_mime_simple(self, data: bytes) -> Optional[str]:
        """简单的魔数检测（不依赖 python-magic）"""
        if len(data) < 4:
            return None
        
        # 常见文件魔数
        MAGIC_NUMBERS = {
            b'\xff\xd8\xff': 'image/jpeg',
            b'\x89PNG\r\n\x1a\n': 'image/png',
            b'GIF87a': 'image/gif',
            b'GIF89a': 'image/gif',
            b'RIFF': 'image/webp',  # 需要进一步检查
            b'BM': 'image/bmp',
            b'%PDF': 'application/pdf',
            b'PK\x03\x04': 'application/zip',
            b'\x1f\x8b': 'application/gzip',
        }
        
        for magic_bytes, mime_type in MAGIC_NUMBERS.items():
            if data.startswith(magic_bytes):
                return mime_type
        
        return None
    
    def _mime_matches_extension(self, mime: str, ext: str) -> bool:
        """检查MIME类型与扩展名是否匹配"""
        expected_exts = MIME_EXTENSION_MAP.get(mime, set())
        # 如果没有映射，则认为匹配
        return not expected_exts or ext in expected_exts
    
    def _validate_image(self, data: bytes) -> tuple:
        """验证图片"""
        errors = []
        image_info = None
        
        try:
            from PIL import Image
            
            img = Image.open(BytesIO(data))
            width, height = img.size
            pixels = width * height
            
            image_info = {
                'width': width,
                'height': height,
                'pixels': pixels,
                'format': img.format,
                'mode': img.mode,
            }
            
            if self.config.image_max_width and width > self.config.image_max_width:
                errors.append(
                    f"图片宽度 {width} 超过限制 {self.config.image_max_width}"
                )
            
            if self.config.image_max_height and height > self.config.image_max_height:
                errors.append(
                    f"图片高度 {height} 超过限制 {self.config.image_max_height}"
                )
            
            if self.config.image_max_pixels and pixels > self.config.image_max_pixels:
                errors.append(
                    f"图片像素数 {pixels} 超过限制 {self.config.image_max_pixels}"
                )
        
        except ImportError:
            logger.debug("Pillow 未安装，跳过图片验证")
        except Exception as e:
            errors.append(f"图片验证失败: {e}")
        
        return errors, image_info
    
    def _run_custom_validators(
        self,
        data: bytes,
        filename: str,
        content_type: Optional[str],
    ) -> List[str]:
        """运行自定义验证器"""
        errors = []
        
        for validator in self.config.custom_validators:
            try:
                result = validator(data, filename, content_type)
                if isinstance(result, str):
                    errors.append(result)
                elif result is False:
                    errors.append("自定义验证失败")
            except Exception as e:
                errors.append(f"自定义验证异常: {e}")
        
        return errors
    
    def _get_extension(self, filename: str) -> str:
        """获取文件扩展名"""
        if '.' in filename:
            return '.' + filename.rsplit('.', 1)[-1]
        return ''


class ValidatedStorageMixin:
    """带验证功能的存储Mixin
    
    为存储后端添加自动文件验证功能。
    
    Example:
        class ValidatedLocalStorage(ValidatedStorageMixin, LocalStorage):
            pass
        
        storage = ValidatedLocalStorage(
            '/data/uploads',
            validator=FileValidator(preset='image'),
        )
        storage.save('avatar.jpg', file_content)  # 自动验证
    """
    
    def __init__(self, *args, validator: Optional[FileValidator] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.validator = validator
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        validate: bool = True,
        **kwargs,
    ) -> str:
        """保存文件（带验证）
        
        Args:
            path: 存储路径
            content: 文件内容
            content_type: MIME类型
            validate: 是否验证（默认True）
            **kwargs: 其他参数传递给父类
            
        Returns:
            str: 存储路径
            
        Raises:
            FileValidationError: 验证失败
        """
        if validate and self.validator:
            # 获取文件名用于验证
            filename = path.split('/')[-1]
            
            result = self.validator.validate(content, filename, content_type)
            if not result.valid:
                raise FileValidationError(result.errors, result.warnings)
            
            # 使用检测到的MIME类型
            if result.detected_mime and not content_type:
                content_type = result.detected_mime
        
        return super().save(path, content, content_type=content_type, **kwargs)


__all__ = [
    'FileValidationConfig',
    'ValidationResult',
    'FileValidator',
    'ValidatedStorageMixin',
    'MIME_EXTENSION_MAP',
    'IMAGE_EXTENSIONS',
]
