# -*- coding: utf-8 -*-
"""安全URL生成器测试"""

import pytest
import time
from datetime import datetime, timedelta

from yweb.storage.secure_url import (
    SecureURLGenerator,
    SecureURL,
    TokenInfo,
    MemoryTokenStore,
)


class TestSecureURLGenerator:
    """SecureURLGenerator 基本功能测试"""
    
    def setup_method(self):
        self.generator = SecureURLGenerator(
            secret_key="test-secret-key-at-least-32-characters",
            base_url="/api/files",
        )
    
    def test_generate_returns_secure_url(self):
        """测试生成Token访问URL"""
        result = self.generator.generate(
            file_path="test/file.txt",
            expires_in=3600,
        )
        
        assert isinstance(result, SecureURL)
        assert result.file_path == "test/file.txt"
        assert result.token is not None
        assert len(result.token) > 20
        assert result.url.startswith("/api/files/t/")
        assert result.expires_at > datetime.now()
    
    def test_generate_with_user_id(self):
        """测试生成带用户限制的URL"""
        result = self.generator.generate(
            file_path="private/doc.pdf",
            user_id=123,
        )
        
        # 验证时需要正确的用户ID
        info = self.generator.validate_token(result.token, user_id=123)
        assert info is not None
        assert info.file_path == "private/doc.pdf"
        assert info.user_id == 123
    
    def test_generate_with_download_options(self):
        """测试生成带下载选项的URL"""
        result = self.generator.generate(
            file_path="report.pdf",
            download=True,
            filename="季度报告.pdf",
            max_downloads=3,
        )
        
        info = self.generator.validate_token(result.token)
        assert info.download is True
        assert info.filename == "季度报告.pdf"
        assert info.max_downloads == 3
    
    def test_generate_with_metadata(self):
        """测试生成带元数据的URL"""
        metadata = {"source": "api", "client": "web"}
        result = self.generator.generate(
            file_path="data.json",
            metadata=metadata,
        )
        
        info = self.generator.validate_token(result.token)
        assert info.metadata == metadata


class TestTokenValidation:
    """Token验证测试"""
    
    def setup_method(self):
        self.generator = SecureURLGenerator(
            secret_key="test-secret-key-at-least-32-characters",
        )
    
    def test_validate_valid_token(self):
        """测试验证有效Token"""
        result = self.generator.generate("test/file.txt")
        
        info = self.generator.validate_token(result.token)
        
        assert info is not None
        assert info.file_path == "test/file.txt"
    
    def test_validate_nonexistent_token(self):
        """测试验证不存在的Token"""
        info = self.generator.validate_token("nonexistent-token")
        assert info is None
    
    def test_validate_expired_token(self):
        """测试验证过期Token"""
        result = self.generator.generate(
            "test/file.txt",
            expires_in=1,  # 1秒后过期
        )
        
        time.sleep(1.5)  # 等待过期
        
        info = self.generator.validate_token(result.token)
        assert info is None
    
    def test_validate_wrong_user_id(self):
        """测试验证错误用户ID"""
        result = self.generator.generate(
            "private/file.txt",
            user_id=123,
        )
        
        # 使用错误的用户ID
        info = self.generator.validate_token(result.token, user_id=456)
        assert info is None
        
        # 不提供用户ID
        info = self.generator.validate_token(result.token)
        assert info is None
    
    def test_validate_correct_user_id(self):
        """测试验证正确用户ID"""
        result = self.generator.generate(
            "private/file.txt",
            user_id=123,
        )
        
        info = self.generator.validate_token(result.token, user_id=123)
        assert info is not None
    
    def test_validate_no_user_restriction(self):
        """测试无用户限制的Token"""
        result = self.generator.generate("public/file.txt")
        
        # 任何用户都可以访问
        info = self.generator.validate_token(result.token)
        assert info is not None
        
        info = self.generator.validate_token(result.token, user_id=123)
        assert info is not None


class TestDownloadLimit:
    """下载次数限制测试"""
    
    def setup_method(self):
        self.generator = SecureURLGenerator(
            secret_key="test-secret-key-at-least-32-characters",
        )
    
    def test_max_downloads_limit(self):
        """测试下载次数限制"""
        result = self.generator.generate(
            "file.txt",
            max_downloads=3,
        )
        
        # 前3次验证应该成功
        for i in range(3):
            info = self.generator.validate_token(result.token)
            assert info is not None, f"第{i+1}次验证应该成功"
            assert info.download_count == i + 1
        
        # 第4次验证应该失败
        info = self.generator.validate_token(result.token)
        assert info is None
    
    def test_no_download_limit(self):
        """测试无下载次数限制"""
        result = self.generator.generate("file.txt")
        
        # 多次验证都应该成功
        for _ in range(10):
            info = self.generator.validate_token(result.token)
            assert info is not None


class TestSignedURL:
    """签名URL测试"""
    
    def setup_method(self):
        self.generator = SecureURLGenerator(
            secret_key="test-secret-key-at-least-32-characters",
            base_url="/api/files",
        )
    
    def test_generate_signed_url(self):
        """测试生成签名URL"""
        url = self.generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=3600,
        )
        
        assert url.startswith("/api/files/s/")
        assert "e=" in url
        assert "s=" in url
    
    def test_validate_signed_url(self):
        """测试验证签名URL"""
        url = self.generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=3600,
        )
        
        # 解析URL参数
        path_part = url.split("/s/")[1].split("?")[0]
        params = dict(p.split("=") for p in url.split("?")[1].split("&"))
        
        file_path = self.generator.validate_signed(
            encoded_path=path_part,
            expires=int(params["e"]),
            signature=params["s"],
        )
        
        assert file_path == "public/image.jpg"
    
    def test_validate_expired_signed_url(self):
        """测试验证过期签名URL"""
        url = self.generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=1,  # 1秒后过期
        )
        
        time.sleep(1.5)
        
        path_part = url.split("/s/")[1].split("?")[0]
        params = dict(p.split("=") for p in url.split("?")[1].split("&"))
        
        file_path = self.generator.validate_signed(
            encoded_path=path_part,
            expires=int(params["e"]),
            signature=params["s"],
        )
        
        assert file_path is None
    
    def test_validate_tampered_signature(self):
        """测试验证被篡改的签名"""
        url = self.generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=3600,
        )
        
        path_part = url.split("/s/")[1].split("?")[0]
        params = dict(p.split("=") for p in url.split("?")[1].split("&"))
        
        # 篡改签名
        file_path = self.generator.validate_signed(
            encoded_path=path_part,
            expires=int(params["e"]),
            signature="tampered-signature",
        )
        
        assert file_path is None
    
    def test_validate_tampered_expires(self):
        """测试验证被篡改的过期时间"""
        url = self.generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=3600,
        )
        
        path_part = url.split("/s/")[1].split("?")[0]
        params = dict(p.split("=") for p in url.split("?")[1].split("&"))
        
        # 篡改过期时间（延长1天）
        tampered_expires = int(params["e"]) + 86400
        
        file_path = self.generator.validate_signed(
            encoded_path=path_part,
            expires=tampered_expires,
            signature=params["s"],
        )
        
        assert file_path is None


class TestMemoryTokenStore:
    """内存Token存储测试"""
    
    def setup_method(self):
        self.store = MemoryTokenStore()
    
    def test_set_and_get(self):
        """测试存储和获取Token"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        self.store.set("token123", info, ttl=3600)
        
        result = self.store.get("token123")
        assert result is not None
        assert result.file_path == "test/file.txt"
    
    def test_get_nonexistent(self):
        """测试获取不存在的Token"""
        result = self.store.get("nonexistent")
        assert result is None
    
    def test_get_expired(self):
        """测试获取过期Token"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime.now() - timedelta(hours=1),  # 已过期
        )
        
        self.store.set("expired-token", info, ttl=0)
        
        result = self.store.get("expired-token")
        assert result is None
    
    def test_delete(self):
        """测试删除Token"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        self.store.set("token123", info, ttl=3600)
        self.store.delete("token123")
        
        result = self.store.get("token123")
        assert result is None
    
    def test_increment_downloads(self):
        """测试增加下载计数"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime.now() + timedelta(hours=1),
            download_count=0,
        )
        
        self.store.set("token123", info, ttl=3600)
        
        count1 = self.store.increment_downloads("token123")
        assert count1 == 1
        
        count2 = self.store.increment_downloads("token123")
        assert count2 == 2
    
    def test_increment_downloads_nonexistent(self):
        """测试增加不存在Token的下载计数"""
        count = self.store.increment_downloads("nonexistent")
        assert count == 0
    
    def test_clear(self):
        """测试清空存储"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        self.store.set("token1", info, ttl=3600)
        self.store.set("token2", info, ttl=3600)
        
        assert self.store.count() == 2
        
        self.store.clear()
        
        assert self.store.count() == 0


class TestTokenRevocation:
    """Token撤销测试"""
    
    def setup_method(self):
        self.generator = SecureURLGenerator(
            secret_key="test-secret-key-at-least-32-characters",
        )
    
    def test_revoke_token(self):
        """测试撤销Token"""
        result = self.generator.generate("test/file.txt")
        
        # 撤销前可以验证
        info = self.generator.validate_token(result.token)
        assert info is not None
        
        # 撤销Token
        self.generator.revoke(result.token)
        
        # 撤销后不能验证
        info = self.generator.validate_token(result.token)
        assert info is None


class TestSecureURLDataclass:
    """SecureURL 数据类测试"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        url = SecureURL(
            url="/api/files/t/abc123",
            token="abc123",
            expires_at=datetime(2024, 1, 15, 12, 0, 0),
            file_path="test/file.txt",
        )
        
        data = url.to_dict()
        
        assert data['url'] == "/api/files/t/abc123"
        assert data['token'] == "abc123"
        assert data['expires_at'] == "2024-01-15T12:00:00"
        assert data['file_path'] == "test/file.txt"


class TestTokenInfoDataclass:
    """TokenInfo 数据类测试"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        info = TokenInfo(
            file_path="test/file.txt",
            expires_at=datetime(2024, 1, 15, 12, 0, 0),
            user_id=123,
            download=True,
            filename="report.pdf",
            max_downloads=5,
            download_count=2,
            metadata={"key": "value"},
        )
        
        data = info.to_dict()
        
        assert data['file_path'] == "test/file.txt"
        assert data['user_id'] == 123
        assert data['download'] is True
        assert data['filename'] == "report.pdf"
        assert data['max_downloads'] == 5
        assert data['download_count'] == 2
        assert data['metadata'] == {"key": "value"}
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            'file_path': "test/file.txt",
            'expires_at': "2024-01-15T12:00:00",
            'user_id': 123,
            'download': True,
            'filename': "report.pdf",
            'max_downloads': 5,
            'download_count': 2,
            'metadata': {"key": "value"},
        }
        
        info = TokenInfo.from_dict(data)
        
        assert info.file_path == "test/file.txt"
        assert info.user_id == 123
        assert info.download is True
        assert info.filename == "report.pdf"
        assert info.max_downloads == 5
        assert info.download_count == 2
        assert info.metadata == {"key": "value"}
