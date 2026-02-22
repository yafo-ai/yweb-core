# -*- coding: utf-8 -*-
"""文件验证器测试"""

import pytest
from io import BytesIO

from yweb.storage.validators import (
    FileValidator,
    FileValidationConfig,
    ValidationResult,
    ValidatedStorageMixin,
)
from yweb.storage import MemoryStorage
from yweb.storage.exceptions import FileValidationError


class TestFileValidationConfig:
    """验证配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = FileValidationConfig()
        
        assert config.max_size is None
        assert config.min_size == 0
        assert len(config.allowed_extensions) == 0
        assert config.verify_magic is True
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = FileValidationConfig(
            max_size=1024 * 1024,
            allowed_extensions={'.jpg', '.png'},
            image_max_width=1920,
        )
        
        assert config.max_size == 1024 * 1024
        assert '.jpg' in config.allowed_extensions
        assert config.image_max_width == 1920


class TestFileValidatorPresets:
    """预设配置测试"""
    
    def test_image_preset(self):
        """测试图片预设"""
        validator = FileValidator(preset='image')
        
        assert validator.config.max_size == 10 * 1024 * 1024
        assert '.jpg' in validator.config.allowed_extensions
        assert 'image/jpeg' in validator.config.allowed_mimes
    
    def test_document_preset(self):
        """测试文档预设"""
        validator = FileValidator(preset='document')
        
        assert validator.config.max_size == 50 * 1024 * 1024
        assert '.pdf' in validator.config.allowed_extensions
    
    def test_avatar_preset(self):
        """测试头像预设"""
        validator = FileValidator(preset='avatar')
        
        assert validator.config.max_size == 2 * 1024 * 1024
        assert validator.config.image_max_width == 4096
    
    def test_video_preset(self):
        """测试视频预设"""
        validator = FileValidator(preset='video')
        
        assert validator.config.max_size == 500 * 1024 * 1024
        assert '.mp4' in validator.config.allowed_extensions
    
    def test_invalid_preset_raises(self):
        """测试无效预设抛出异常"""
        with pytest.raises(ValueError) as exc_info:
            FileValidator(preset='invalid')
        
        assert 'invalid' in str(exc_info.value)


class TestFileSizeValidation:
    """文件大小验证测试"""
    
    def test_valid_size(self):
        """测试有效大小"""
        config = FileValidationConfig(max_size=1024, min_size=10)
        validator = FileValidator(config=config)
        
        result = validator.validate(b'x' * 100, 'test.txt')
        
        assert result.valid is True
        assert result.size == 100
    
    def test_file_too_large(self):
        """测试文件过大"""
        config = FileValidationConfig(max_size=100)
        validator = FileValidator(config=config)
        
        result = validator.validate(b'x' * 200, 'test.txt')
        
        assert result.valid is False
        assert any('超过限制' in e for e in result.errors)
    
    def test_file_too_small(self):
        """测试文件过小"""
        config = FileValidationConfig(min_size=100)
        validator = FileValidator(config=config)
        
        result = validator.validate(b'x' * 50, 'test.txt')
        
        assert result.valid is False
        assert any('小于最小要求' in e for e in result.errors)


class TestExtensionValidation:
    """扩展名验证测试"""
    
    def test_allowed_extension(self):
        """测试允许的扩展名"""
        config = FileValidationConfig(
            allowed_extensions={'.txt', '.pdf'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'document.pdf')
        
        assert result.valid is True
    
    def test_disallowed_extension(self):
        """测试不允许的扩展名"""
        config = FileValidationConfig(
            allowed_extensions={'.jpg', '.png'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'script.exe')
        
        assert result.valid is False
        assert any('不允许的文件扩展名' in e for e in result.errors)
    
    def test_blocked_extension(self):
        """测试禁止的扩展名"""
        config = FileValidationConfig(
            blocked_extensions={'.exe', '.sh'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'virus.exe')
        
        assert result.valid is False
        assert any('禁止的文件扩展名' in e for e in result.errors)
    
    def test_no_extension(self):
        """测试无扩展名文件"""
        config = FileValidationConfig(
            allowed_extensions={'.txt'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'noext')
        
        assert result.valid is False


class TestMimeValidation:
    """MIME类型验证测试"""
    
    def test_allowed_declared_mime(self):
        """测试允许的声明MIME类型"""
        config = FileValidationConfig(
            allowed_mimes={'text/plain'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'test.txt', content_type='text/plain')
        
        assert result.valid is True
    
    def test_blocked_declared_mime(self):
        """测试禁止的声明MIME类型"""
        config = FileValidationConfig(
            blocked_mimes={'application/x-executable'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(
            b'content', 'test.exe', content_type='application/x-executable'
        )
        
        assert result.valid is False
        assert any('禁止的MIME类型' in e for e in result.errors)


class TestMagicValidation:
    """魔数验证测试"""
    
    def test_jpeg_magic(self):
        """测试JPEG魔数"""
        # JPEG 文件魔数
        jpeg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        
        config = FileValidationConfig(verify_magic=True)
        validator = FileValidator(config=config)
        
        result = validator.validate(jpeg_header + b'x' * 100, 'test.jpg')
        
        assert result.detected_mime == 'image/jpeg'
    
    def test_png_magic(self):
        """测试PNG魔数"""
        # PNG 文件魔数
        png_header = b'\x89PNG\r\n\x1a\n'
        
        config = FileValidationConfig(verify_magic=True)
        validator = FileValidator(config=config)
        
        result = validator.validate(png_header + b'x' * 100, 'test.png')
        
        assert result.detected_mime == 'image/png'
    
    def test_pdf_magic(self):
        """测试PDF魔数"""
        pdf_header = b'%PDF-1.4'
        
        config = FileValidationConfig(verify_magic=True)
        validator = FileValidator(config=config)
        
        result = validator.validate(pdf_header + b'x' * 100, 'test.pdf')
        
        assert result.detected_mime == 'application/pdf'
    
    def test_extension_mime_mismatch_warning(self):
        """测试扩展名与实际类型不匹配产生警告"""
        # 使用 PNG 魔数但 JPG 扩展名
        png_header = b'\x89PNG\r\n\x1a\n'
        
        config = FileValidationConfig(verify_magic=True)
        validator = FileValidator(config=config)
        
        result = validator.validate(png_header + b'x' * 100, 'fake.jpg')
        
        assert any('不匹配' in w for w in result.warnings)


class TestCustomValidators:
    """自定义验证器测试"""
    
    def test_custom_validator_pass(self):
        """测试自定义验证器通过"""
        def check_content(data, filename, content_type):
            return None  # 返回 None 表示通过
        
        config = FileValidationConfig(
            custom_validators=[check_content],
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'valid content', 'test.txt')
        
        assert result.valid is True
    
    def test_custom_validator_fail_with_message(self):
        """测试自定义验证器返回错误消息"""
        def check_content(data, filename, content_type):
            return "内容不合法"  # 返回字符串表示错误
        
        config = FileValidationConfig(
            custom_validators=[check_content],
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'invalid', 'test.txt')
        
        assert result.valid is False
        assert '内容不合法' in result.errors
    
    def test_custom_validator_fail_with_false(self):
        """测试自定义验证器返回False"""
        def check_content(data, filename, content_type):
            return False  # 返回 False 表示失败
        
        config = FileValidationConfig(
            custom_validators=[check_content],
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'invalid', 'test.txt')
        
        assert result.valid is False
        assert any('自定义验证失败' in e for e in result.errors)
    
    def test_custom_validator_exception(self):
        """测试自定义验证器抛出异常"""
        def check_content(data, filename, content_type):
            raise ValueError("验证错误")
        
        config = FileValidationConfig(
            custom_validators=[check_content],
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'content', 'test.txt')
        
        assert result.valid is False
        assert any('验证错误' in e for e in result.errors)


class TestValidationResult:
    """验证结果测试"""
    
    def test_raise_if_invalid(self):
        """测试 raise_if_invalid"""
        result = ValidationResult(
            valid=False,
            errors=['错误1', '错误2'],
            warnings=[],
            size=100,
        )
        
        with pytest.raises(FileValidationError) as exc_info:
            result.raise_if_invalid()
        
        assert '错误1' in str(exc_info.value)
    
    def test_raise_if_valid(self):
        """测试验证通过时不抛出异常"""
        result = ValidationResult(
            valid=True,
            errors=[],
            warnings=['警告'],
            size=100,
        )
        
        # 不应该抛出异常
        result.raise_if_invalid()
    
    def test_validate_or_raise(self):
        """测试 validate_or_raise"""
        config = FileValidationConfig(max_size=10, verify_magic=False)
        validator = FileValidator(config=config)
        
        with pytest.raises(FileValidationError):
            validator.validate_or_raise(b'x' * 100, 'test.txt')


class TestFileObjectInput:
    """文件对象输入测试"""
    
    def test_validate_file_object(self):
        """测试验证文件对象"""
        config = FileValidationConfig(max_size=1024, verify_magic=False)
        validator = FileValidator(config=config)
        
        file_obj = BytesIO(b'file content')
        
        result = validator.validate(file_obj, 'test.txt')
        
        assert result.valid is True
        assert result.size == 12
        
        # 文件对象位置应该被还原
        assert file_obj.tell() == 0
    
    def test_validate_file_object_preserves_position(self):
        """测试验证后文件对象位置被保留"""
        config = FileValidationConfig(verify_magic=False)
        validator = FileValidator(config=config)
        
        file_obj = BytesIO(b'file content')
        file_obj.seek(5)  # 移动位置
        
        validator.validate(file_obj, 'test.txt')
        
        # 位置应该恢复到原来的位置
        assert file_obj.tell() == 5


class TestValidatedStorageMixin:
    """ValidatedStorageMixin 测试"""
    
    def test_save_with_validation_pass(self):
        """测试带验证的保存（通过）"""
        # 创建带验证的存储类
        class ValidatedMemoryStorage(ValidatedStorageMixin, MemoryStorage):
            pass
        
        validator = FileValidator(config=FileValidationConfig(
            max_size=1024,
            verify_magic=False,
        ))
        storage = ValidatedMemoryStorage(validator=validator)
        
        result = storage.save('test.txt', b'content')
        
        assert result == 'test.txt'
        assert storage.exists('test.txt')
    
    def test_save_with_validation_fail(self):
        """测试带验证的保存（失败）"""
        class ValidatedMemoryStorage(ValidatedStorageMixin, MemoryStorage):
            pass
        
        validator = FileValidator(config=FileValidationConfig(
            max_size=10,
            verify_magic=False,
        ))
        storage = ValidatedMemoryStorage(validator=validator)
        
        with pytest.raises(FileValidationError):
            storage.save('test.txt', b'x' * 100)
    
    def test_save_skip_validation(self):
        """测试跳过验证"""
        class ValidatedMemoryStorage(ValidatedStorageMixin, MemoryStorage):
            pass
        
        validator = FileValidator(config=FileValidationConfig(
            max_size=10,
            verify_magic=False,
        ))
        storage = ValidatedMemoryStorage(validator=validator)
        
        # 使用 validate=False 跳过验证
        result = storage.save('test.txt', b'x' * 100, validate=False)
        
        assert result == 'test.txt'
        assert storage.exists('test.txt')
    
    def test_save_without_validator(self):
        """测试无验证器时直接保存"""
        class ValidatedMemoryStorage(ValidatedStorageMixin, MemoryStorage):
            pass
        
        storage = ValidatedMemoryStorage()  # 无验证器
        
        result = storage.save('test.txt', b'x' * 100)
        
        assert result == 'test.txt'


class TestComplexValidation:
    """复杂验证场景测试"""
    
    def test_multiple_errors(self):
        """测试多个验证错误"""
        config = FileValidationConfig(
            max_size=10,
            allowed_extensions={'.jpg'},
            verify_magic=False,
        )
        validator = FileValidator(config=config)
        
        result = validator.validate(b'x' * 100, 'test.exe')
        
        assert result.valid is False
        assert len(result.errors) >= 2  # 至少两个错误
    
    def test_combined_preset_and_custom(self):
        """测试预设配置与自定义验证器组合"""
        def no_secret(data, filename, content_type):
            if b'secret' in data:
                return "内容包含敏感信息"
            return None
        
        # 从预设创建配置并添加自定义验证器
        config = FileValidator.PRESETS['document']
        config.custom_validators.append(no_secret)
        config.verify_magic = False
        
        validator = FileValidator(config=config)
        
        result = validator.validate(b'this is secret data', 'doc.pdf')
        
        assert result.valid is False
        assert any('敏感信息' in e for e in result.errors)
