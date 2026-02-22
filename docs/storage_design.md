# yweb-storage 虚拟文件系统设计文档

## 1. 概述

### 1.1 背景与目标

在 Web 应用开发中，文件存储是常见需求，包括用户上传的头像、文档、临时文件处理等。不同场景需要不同的存储后端（本地文件系统、云存储、内存缓存等），同时还需要统一的安全访问控制。

**设计目标：**

1. **统一抽象** - 提供统一的文件操作接口，屏蔽底层存储差异
2. **多后端支持** - 支持本地、内存、OSS、S3、MinIO 等多种存储后端
3. **安全访问** - 提供签名URL、Token访问等安全机制，隐藏真实文件路径
4. **易于扩展** - 基于抽象基类，便于添加新的存储后端
5. **与框架集成** - 提供 FastAPI 路由集成，开箱即用

### 1.2 核心概念

| 概念 | 说明 |
|------|------|
| **StorageBackend** | 存储后端抽象基类，定义统一的文件操作接口 |
| **StorageManager** | 存储管理器，管理多个后端实例，提供统一访问入口 |
| **SecureURL** | 安全URL生成器，提供签名URL和Token访问机制 |
| **FileInfo** | 文件元信息数据类，包含路径、大小、类型等 |

---

## 2. 架构设计

### 2.1 模块结构

```
yweb/
└── storage/
    ├── __init__.py              # 公共 API 导出
    ├── base.py                  # 抽象基类、数据类型定义
    ├── manager.py               # 存储管理器
    ├── secure_url.py            # 安全URL生成器
    ├── exceptions.py            # 异常定义
    ├── utils.py                 # 工具函数（MIME类型检测、路径处理等）
    ├── backends/
    │   ├── __init__.py          # 后端导出
    │   ├── memory.py            # 内存存储（临时文件）
    │   ├── local.py             # 本地文件系统
    │   ├── oss.py               # 阿里云 OSS
    │   ├── s3.py                # AWS S3 / MinIO
    │   └── ftp.py               # FTP/SFTP（可选）
    └── integrations/
        ├── __init__.py
        └── fastapi.py           # FastAPI 路由集成
```

### 2.2 类图

```
┌─────────────────────────────────────────────────────────────────┐
│                        StorageManager                            │
│  ─────────────────────────────────────────────────────────────  │
│  + register(name, backend, default)                              │
│  + get(name) -> StorageBackend                                   │
│  + configure(config: dict)                                       │
│  + list_backends() -> List[str]                                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ manages
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    StorageBackend (ABC)                          │
│  ─────────────────────────────────────────────────────────────  │
│  + save(path, content, **kwargs) -> str                         │
│  + read(path) -> BinaryIO                                        │
│  + read_bytes(path) -> bytes                                     │
│  + delete(path) -> bool                                          │
│  + exists(path) -> bool                                          │
│  + get_info(path) -> FileInfo                                    │
│  + list(prefix) -> List[FileInfo]                                │
│  + get_url(path, expires) -> str                                 │
│  + copy(src, dst) -> str                                         │
│  + move(src, dst) -> str                                         │
└─────────────────────────────────────────────────────────────────┘
          ▲                    ▲                    ▲
          │                    │                    │
    ┌─────┴─────┐        ┌─────┴─────┐       ┌─────┴─────┐
    │MemoryStorage│      │LocalStorage│      │OSSStorage │
    └───────────┘        └───────────┘       └───────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     SecureURLGenerator                           │
│  ─────────────────────────────────────────────────────────────  │
│  + generate(path, expires_in, user_id, ...) -> SecureURL        │
│  + generate_signed(path, expires_in) -> str                      │
│  + validate(token, user_id) -> Optional[dict]                    │
│  + validate_signed(path, expires, sign) -> Optional[str]         │
│  + revoke(token)                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 数据流图

```
用户上传文件                                用户请求文件
    │                                           │
    ▼                                           ▼
┌─────────┐                              ┌─────────────┐
│ FastAPI │                              │  安全URL验证  │
│ Endpoint│                              │  (Token/签名) │
└────┬────┘                              └──────┬──────┘
     │                                          │
     ▼                                          ▼ 验证通过
┌──────────────┐                         ┌──────────────┐
│StorageManager│                         │StorageManager│
│   .get()     │                         │   .get()     │
└──────┬───────┘                         └──────┬───────┘
       │                                        │
       ▼                                        ▼
┌──────────────┐                         ┌──────────────┐
│StorageBackend│                         │StorageBackend│
│   .save()    │                         │   .read()    │
└──────┬───────┘                         └──────┬───────┘
       │                                        │
       ▼                                        ▼
   实际存储                                  返回文件
(本地/OSS/内存)                            (流式响应)
```

---

## 3. 详细设计

### 3.1 抽象基类 (base.py)

#### 3.1.1 FileInfo 数据类

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class FileInfo:
    """文件元信息"""
    path: str                                    # 存储路径
    size: int                                    # 文件大小（字节）
    created_at: Optional[datetime] = None        # 创建时间
    modified_at: Optional[datetime] = None       # 修改时间
    content_type: Optional[str] = None           # MIME类型
    etag: Optional[str] = None                   # ETag（用于缓存）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 自定义元数据
    
    @property
    def filename(self) -> str:
        """获取文件名"""
        return self.path.split('/')[-1]
    
    @property
    def extension(self) -> str:
        """获取扩展名"""
        return self.filename.rsplit('.', 1)[-1] if '.' in self.filename else ''
```

#### 3.1.2 StorageBackend 抽象基类

```python
from abc import ABC, abstractmethod
from typing import BinaryIO, List, Optional, Union
from io import BytesIO

class StorageBackend(ABC):
    """存储后端抽象基类
    
    所有存储后端必须实现此接口，保证统一的操作方式。
    """
    
    # ==================== 必须实现的方法 ====================
    
    @abstractmethod
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件
        
        Args:
            path: 存储路径（相对路径）
            content: 文件内容（文件对象或字节）
            content_type: MIME类型，不指定则自动检测
            metadata: 自定义元数据
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 实际存储路径
            
        Raises:
            FileExistsError: overwrite=False 且文件已存在
            StorageError: 存储失败
        """
        pass
    
    @abstractmethod
    def read(self, path: str) -> BinaryIO:
        """读取文件，返回文件对象
        
        Args:
            path: 文件路径
            
        Returns:
            BinaryIO: 可读取的文件对象
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        pass
    
    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 是否删除成功（文件不存在时返回 False）
        """
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        pass
    
    @abstractmethod
    def get_info(self, path: str) -> FileInfo:
        """获取文件信息
        
        Raises:
            FileNotFoundError: 文件不存在
        """
        pass
    
    @abstractmethod
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """列出文件
        
        Args:
            prefix: 路径前缀（目录）
            recursive: 是否递归列出子目录
            limit: 最大返回数量
        """
        pass
    
    # ==================== 可选实现的方法 ====================
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件内容为字节"""
        with self.read(path) as f:
            return f.read()
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
    ) -> str:
        """获取文件访问URL
        
        Args:
            path: 文件路径
            expires: 过期时间（秒）
            download: 是否强制下载
            filename: 下载时的文件名
            
        Returns:
            str: 访问URL
            
        Raises:
            NotImplementedError: 后端不支持URL访问
        """
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 get_url")
    
    def copy(self, src: str, dst: str) -> str:
        """复制文件"""
        content = self.read(src)
        info = self.get_info(src)
        return self.save(dst, content, content_type=info.content_type)
    
    def move(self, src: str, dst: str) -> str:
        """移动文件"""
        result = self.copy(src, dst)
        self.delete(src)
        return result
    
    def get_size(self, path: str) -> int:
        """获取文件大小"""
        return self.get_info(path).size
```

### 3.2 存储后端实现

#### 3.2.1 内存存储 (backends/memory.py)

**适用场景：**
- 临时文件处理
- 单元测试
- 文件上传预处理（验证后再存储到持久化后端）

```python
import threading
from io import BytesIO
from datetime import datetime
from typing import Dict, Optional, List, Union, BinaryIO
from collections import OrderedDict
import hashlib

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageError


class MemoryStorage(StorageBackend):
    """内存存储后端
    
    特点：
    - 数据存储在内存中，重启后丢失
    - 支持 LRU 淘汰策略
    - 线程安全
    - 适合临时文件、测试场景
    
    使用示例:
        storage = MemoryStorage(max_size=100*1024*1024)  # 100MB
        storage.save("temp/upload.jpg", file_content)
        content = storage.read("temp/upload.jpg")
    """
    
    def __init__(
        self,
        max_size: int = 100 * 1024 * 1024,  # 默认100MB
        max_files: int = 10000,              # 最大文件数
        auto_cleanup: bool = True,           # 自动清理过期文件
    ):
        self._files: OrderedDict[str, bytes] = OrderedDict()
        self._metadata: Dict[str, FileInfo] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._max_files = max_files
        self._current_size = 0
        self._auto_cleanup = auto_cleanup
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        # 读取内容
        if isinstance(content, bytes):
            data = content
        else:
            data = content.read()
        
        with self._lock:
            # 检查是否已存在
            if not overwrite and path in self._files:
                raise FileExistsError(f"文件已存在: {path}")
            
            # 如果是覆盖，先减去原文件大小
            if path in self._files:
                self._current_size -= len(self._files[path])
            
            # 检查容量，必要时清理
            while (self._current_size + len(data) > self._max_size or 
                   len(self._files) >= self._max_files):
                if not self._files:
                    raise StorageError("内存存储空间不足")
                self._evict_oldest()
            
            # 存储文件
            self._files[path] = data
            self._files.move_to_end(path)  # LRU: 移到末尾
            
            # 计算 ETag
            etag = hashlib.md5(data).hexdigest()
            
            # 存储元信息
            now = datetime.now()
            self._metadata[path] = FileInfo(
                path=path,
                size=len(data),
                created_at=self._metadata.get(path, FileInfo(path, 0)).created_at or now,
                modified_at=now,
                content_type=content_type or self._guess_content_type(path),
                etag=etag,
                metadata=metadata or {},
            )
            
            self._current_size += len(data)
        
        return path
    
    def read(self, path: str) -> BinaryIO:
        with self._lock:
            if path not in self._files:
                raise FileNotFoundError(f"文件不存在: {path}")
            
            # LRU: 访问后移到末尾
            self._files.move_to_end(path)
            
            return BytesIO(self._files[path])
    
    def delete(self, path: str) -> bool:
        with self._lock:
            if path not in self._files:
                return False
            
            self._current_size -= len(self._files[path])
            del self._files[path]
            del self._metadata[path]
            return True
    
    def exists(self, path: str) -> bool:
        return path in self._files
    
    def get_info(self, path: str) -> FileInfo:
        with self._lock:
            if path not in self._metadata:
                raise FileNotFoundError(f"文件不存在: {path}")
            return self._metadata[path]
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        with self._lock:
            results = []
            for path, info in self._metadata.items():
                if path.startswith(prefix):
                    # 非递归时只返回直接子文件
                    if not recursive:
                        relative = path[len(prefix):].lstrip('/')
                        if '/' in relative:
                            continue
                    results.append(info)
                    if limit and len(results) >= limit:
                        break
            return results
    
    def _evict_oldest(self):
        """淘汰最老的文件（LRU）"""
        if self._files:
            oldest_path = next(iter(self._files))
            self._current_size -= len(self._files[oldest_path])
            del self._files[oldest_path]
            del self._metadata[oldest_path]
    
    def _guess_content_type(self, path: str) -> str:
        """根据文件名猜测 MIME 类型"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(path)
        return content_type or 'application/octet-stream'
    
    # ==================== 内存存储特有方法 ====================
    
    def clear(self):
        """清空所有文件"""
        with self._lock:
            self._files.clear()
            self._metadata.clear()
            self._current_size = 0
    
    def get_stats(self) -> dict:
        """获取存储统计信息"""
        with self._lock:
            return {
                'file_count': len(self._files),
                'total_size': self._current_size,
                'max_size': self._max_size,
                'usage_percent': (self._current_size / self._max_size * 100) if self._max_size else 0,
            }
```

#### 3.2.2 本地存储 (backends/local.py)

**适用场景：**
- 开发环境
- 小规模部署
- 文件需要直接访问的场景

```python
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Union, BinaryIO
import hashlib
import mimetypes

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageError


class LocalStorage(StorageBackend):
    """本地文件系统存储后端
    
    特点：
    - 直接使用文件系统存储
    - 支持路径安全检查（防止路径穿越）
    - 自动创建目录
    
    使用示例:
        storage = LocalStorage("/data/uploads")
        storage.save("images/avatar.jpg", file_content)
        url = storage.get_url("images/avatar.jpg")  # 需要配置 base_url
    """
    
    def __init__(
        self,
        base_path: str,
        base_url: Optional[str] = None,  # 用于生成访问URL
        create_dirs: bool = True,
        permissions: int = 0o644,         # 文件权限
        dir_permissions: int = 0o755,     # 目录权限
    ):
        self.base_path = Path(base_path).resolve()
        self.base_url = base_url.rstrip('/') if base_url else None
        self.permissions = permissions
        self.dir_permissions = dir_permissions
        
        if create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径（防止路径穿越攻击）"""
        # 规范化路径
        clean_path = Path(path).as_posix().lstrip('/')
        full_path = (self.base_path / clean_path).resolve()
        
        # 安全检查：确保路径在 base_path 内
        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise StorageError(f"非法路径: {path}")
        
        return full_path
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        full_path = self._resolve_path(path)
        
        # 检查是否已存在
        if not overwrite and full_path.exists():
            raise FileExistsError(f"文件已存在: {path}")
        
        # 创建目录
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        if isinstance(content, bytes):
            full_path.write_bytes(content)
        else:
            with open(full_path, 'wb') as f:
                shutil.copyfileobj(content, f)
        
        # 设置权限
        os.chmod(full_path, self.permissions)
        
        return path
    
    def read(self, path: str) -> BinaryIO:
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        return open(full_path, 'rb')
    
    def read_bytes(self, path: str) -> bytes:
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        return full_path.read_bytes()
    
    def delete(self, path: str) -> bool:
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            return False
        
        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()
        
        return True
    
    def exists(self, path: str) -> bool:
        full_path = self._resolve_path(path)
        return full_path.exists()
    
    def get_info(self, path: str) -> FileInfo:
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        stat = full_path.stat()
        content_type, _ = mimetypes.guess_type(str(full_path))
        
        # 计算 ETag
        with open(full_path, 'rb') as f:
            etag = hashlib.md5(f.read()).hexdigest()
        
        return FileInfo(
            path=path,
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=content_type,
            etag=etag,
        )
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        base = self._resolve_path(prefix) if prefix else self.base_path
        
        if not base.exists():
            return []
        
        results = []
        
        if recursive:
            iterator = base.rglob('*')
        else:
            iterator = base.glob('*')
        
        for full_path in iterator:
            if full_path.is_file():
                relative_path = str(full_path.relative_to(self.base_path))
                try:
                    results.append(self.get_info(relative_path))
                except Exception:
                    continue
                
                if limit and len(results) >= limit:
                    break
        
        return results
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
    ) -> str:
        """获取文件URL（仅当配置了 base_url 时有效）"""
        if not self.base_url:
            raise NotImplementedError("未配置 base_url，无法生成访问URL")
        
        # 确保文件存在
        if not self.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        
        return f"{self.base_url}/{path}"
    
    # ==================== 本地存储特有方法 ====================
    
    def get_absolute_path(self, path: str) -> str:
        """获取文件的绝对路径"""
        return str(self._resolve_path(path))
```

#### 3.2.3 阿里云 OSS 存储 (backends/oss.py)

**适用场景：**
- 生产环境
- 大文件存储
- CDN 加速

```python
from typing import Optional, List, Union, BinaryIO
from datetime import datetime
from io import BytesIO

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageError


class OSSStorage(StorageBackend):
    """阿里云 OSS 存储后端
    
    依赖: pip install oss2
    
    使用示例:
        storage = OSSStorage(
            access_key_id="your-key-id",
            access_key_secret="your-key-secret",
            endpoint="oss-cn-hangzhou.aliyuncs.com",
            bucket_name="your-bucket",
            prefix="uploads/",  # 可选：文件存储前缀
        )
        
        # 保存文件
        storage.save("images/avatar.jpg", file_content)
        
        # 获取签名URL（1小时有效）
        url = storage.get_url("images/avatar.jpg", expires=3600)
    """
    
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
        prefix: str = "",
        internal_endpoint: Optional[str] = None,  # 内网端点
        connect_timeout: int = 30,
    ):
        try:
            import oss2
        except ImportError:
            raise ImportError("请安装 oss2: pip install oss2")
        
        self.prefix = prefix.strip('/')
        
        # 创建认证和 Bucket
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, endpoint, bucket_name, connect_timeout=connect_timeout)
        
        # 内网 Bucket（用于服务器间传输）
        if internal_endpoint:
            self.internal_bucket = oss2.Bucket(auth, internal_endpoint, bucket_name)
        else:
            self.internal_bucket = None
    
    def _full_key(self, path: str) -> str:
        """构建完整的 OSS key"""
        path = path.lstrip('/')
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path
    
    def _strip_prefix(self, key: str) -> str:
        """从 key 中移除前缀"""
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        import oss2
        
        key = self._full_key(path)
        
        # 检查是否已存在
        if not overwrite and self.exists(path):
            raise FileExistsError(f"文件已存在: {path}")
        
        # 准备 headers
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        if metadata:
            for k, v in metadata.items():
                headers[f'x-oss-meta-{k}'] = str(v)
        
        # 上传
        if isinstance(content, bytes):
            self.bucket.put_object(key, content, headers=headers)
        else:
            self.bucket.put_object(key, content, headers=headers)
        
        return path
    
    def read(self, path: str) -> BinaryIO:
        key = self._full_key(path)
        
        try:
            result = self.bucket.get_object(key)
            return BytesIO(result.read())
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise FileNotFoundError(f"文件不存在: {path}")
            raise StorageError(f"读取文件失败: {e}")
    
    def delete(self, path: str) -> bool:
        key = self._full_key(path)
        
        try:
            self.bucket.delete_object(key)
            return True
        except Exception:
            return False
    
    def exists(self, path: str) -> bool:
        key = self._full_key(path)
        return self.bucket.object_exists(key)
    
    def get_info(self, path: str) -> FileInfo:
        key = self._full_key(path)
        
        try:
            meta = self.bucket.head_object(key)
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise FileNotFoundError(f"文件不存在: {path}")
            raise
        
        # 解析自定义元数据
        metadata = {}
        for k, v in meta.headers.items():
            if k.lower().startswith('x-oss-meta-'):
                metadata[k[11:]] = v
        
        return FileInfo(
            path=path,
            size=meta.content_length,
            created_at=None,  # OSS 不提供创建时间
            modified_at=datetime.strptime(
                meta.headers.get('Last-Modified', ''),
                '%a, %d %b %Y %H:%M:%S GMT'
            ) if meta.headers.get('Last-Modified') else None,
            content_type=meta.content_type,
            etag=meta.etag.strip('"'),
            metadata=metadata,
        )
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        import oss2
        
        full_prefix = self._full_key(prefix) if prefix else self.prefix
        if full_prefix:
            full_prefix = full_prefix.rstrip('/') + '/'
        
        delimiter = '' if recursive else '/'
        
        results = []
        for obj in oss2.ObjectIterator(self.bucket, prefix=full_prefix, delimiter=delimiter):
            if obj.is_prefix():  # 目录
                continue
            
            results.append(FileInfo(
                path=self._strip_prefix(obj.key),
                size=obj.size,
                modified_at=datetime.fromtimestamp(obj.last_modified) if obj.last_modified else None,
                etag=obj.etag.strip('"') if obj.etag else None,
            ))
            
            if limit and len(results) >= limit:
                break
        
        return results
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
        internal: bool = False,
    ) -> str:
        """获取签名URL
        
        Args:
            path: 文件路径
            expires: 过期时间（秒）
            download: 是否强制下载
            filename: 下载时的文件名
            internal: 是否使用内网地址
        """
        key = self._full_key(path)
        bucket = self.internal_bucket if internal and self.internal_bucket else self.bucket
        
        params = {}
        if download:
            disposition = 'attachment'
            if filename:
                # URL 编码文件名
                from urllib.parse import quote
                disposition += f"; filename*=UTF-8''{quote(filename)}"
            params['response-content-disposition'] = disposition
        
        return bucket.sign_url('GET', key, expires, params=params)
    
    # ==================== OSS 特有方法 ====================
    
    def get_upload_url(self, path: str, expires: int = 3600, content_type: Optional[str] = None) -> str:
        """获取预签名上传URL（用于客户端直传）"""
        key = self._full_key(path)
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        return self.bucket.sign_url('PUT', key, expires, headers=headers)
```

### 3.3 存储管理器 (manager.py)

```python
from typing import Dict, Optional, Type, Any
import logging

from .base import StorageBackend
from .exceptions import StorageError

logger = logging.getLogger(__name__)


class StorageManager:
    """存储管理器
    
    管理多个存储后端实例，提供统一的访问入口。
    支持：
    - 多后端注册与切换
    - 配置文件初始化
    - 默认后端设置
    
    使用示例:
        # 方式1：手动注册
        StorageManager.register('local', LocalStorage('/data/uploads'))
        StorageManager.register('oss', OSSStorage(...), default=True)
        
        # 方式2：配置文件初始化
        StorageManager.configure({
            'local': {'type': 'local', 'base_path': '/data/uploads'},
            'oss': {'type': 'oss', 'access_key_id': '...', ...},
            'default': 'oss'
        })
        
        # 使用
        storage = StorageManager.get()  # 获取默认后端
        storage = StorageManager.get('local')  # 获取指定后端
    """
    
    _backends: Dict[str, StorageBackend] = {}
    _default: Optional[str] = None
    _backend_classes: Dict[str, Type[StorageBackend]] = {}
    
    @classmethod
    def register(
        cls,
        name: str,
        backend: StorageBackend,
        default: bool = False
    ) -> None:
        """注册存储后端
        
        Args:
            name: 后端名称
            backend: 后端实例
            default: 是否设为默认
        """
        cls._backends[name] = backend
        
        if default or cls._default is None:
            cls._default = name
        
        logger.info(f"注册存储后端: {name} ({backend.__class__.__name__})")
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """注销存储后端"""
        if name in cls._backends:
            del cls._backends[name]
            if cls._default == name:
                cls._default = next(iter(cls._backends), None)
    
    @classmethod
    def get(cls, name: Optional[str] = None) -> StorageBackend:
        """获取存储后端
        
        Args:
            name: 后端名称，为空时返回默认后端
            
        Raises:
            StorageError: 后端未注册
        """
        name = name or cls._default
        
        if not name:
            raise StorageError("未配置任何存储后端")
        
        if name not in cls._backends:
            raise StorageError(f"存储后端未注册: {name}")
        
        return cls._backends[name]
    
    @classmethod
    def set_default(cls, name: str) -> None:
        """设置默认后端"""
        if name not in cls._backends:
            raise StorageError(f"存储后端未注册: {name}")
        cls._default = name
    
    @classmethod
    def list_backends(cls) -> Dict[str, str]:
        """列出所有已注册的后端"""
        return {
            name: backend.__class__.__name__
            for name, backend in cls._backends.items()
        }
    
    @classmethod
    def register_backend_class(cls, type_name: str, backend_class: Type[StorageBackend]) -> None:
        """注册后端类（用于配置文件初始化）"""
        cls._backend_classes[type_name] = backend_class
    
    @classmethod
    def configure(cls, config: Dict[str, Any]) -> None:
        """从配置初始化所有后端
        
        配置格式:
            {
                'local': {
                    'type': 'local',
                    'base_path': '/data/uploads',
                    ...
                },
                'oss': {
                    'type': 'oss',
                    'access_key_id': '...',
                    ...
                },
                'default': 'oss'  # 可选
            }
        """
        # 注册默认后端类
        cls._register_default_backend_classes()
        
        default_name = config.pop('default', None)
        
        for name, backend_config in config.items():
            backend_config = dict(backend_config)  # 复制，避免修改原配置
            type_name = backend_config.pop('type')
            
            if type_name not in cls._backend_classes:
                raise StorageError(f"未知的存储后端类型: {type_name}")
            
            backend_class = cls._backend_classes[type_name]
            backend = backend_class(**backend_config)
            
            is_default = (name == default_name) or (default_name is None and not cls._backends)
            cls.register(name, backend, default=is_default)
    
    @classmethod
    def _register_default_backend_classes(cls) -> None:
        """注册默认后端类"""
        if cls._backend_classes:
            return
        
        from .backends.memory import MemoryStorage
        from .backends.local import LocalStorage
        
        cls._backend_classes['memory'] = MemoryStorage
        cls._backend_classes['local'] = LocalStorage
        
        # 可选后端
        try:
            from .backends.oss import OSSStorage
            cls._backend_classes['oss'] = OSSStorage
        except ImportError:
            pass
        
        try:
            from .backends.s3 import S3Storage
            cls._backend_classes['s3'] = S3Storage
        except ImportError:
            pass
    
    @classmethod
    def reset(cls) -> None:
        """重置所有配置（主要用于测试）"""
        cls._backends.clear()
        cls._default = None
```

### 3.4 安全URL生成器 (secure_url.py)

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
import hashlib
import hmac
import base64
import secrets
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class SecureURL:
    """安全访问URL"""
    url: str                          # 完整访问URL
    token: str                        # 访问令牌
    expires_at: datetime              # 过期时间
    file_path: str                    # 原始文件路径


@dataclass  
class TokenInfo:
    """Token信息"""
    file_path: str
    expires_at: datetime
    user_id: Optional[int] = None
    download: bool = False
    filename: Optional[str] = None
    max_downloads: Optional[int] = None
    download_count: int = 0
    metadata: Dict[str, Any] = None


class TokenStore:
    """Token存储接口"""
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        raise NotImplementedError
    
    def get(self, token: str) -> Optional[TokenInfo]:
        raise NotImplementedError
    
    def delete(self, token: str) -> None:
        raise NotImplementedError
    
    def increment_downloads(self, token: str) -> int:
        raise NotImplementedError


class MemoryTokenStore(TokenStore):
    """内存Token存储（开发/测试用）"""
    
    def __init__(self):
        self._store: Dict[str, TokenInfo] = {}
        self._lock = threading.RLock()
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        with self._lock:
            self._store[token] = info
    
    def get(self, token: str) -> Optional[TokenInfo]:
        with self._lock:
            info = self._store.get(token)
            if info and datetime.now() > info.expires_at:
                del self._store[token]
                return None
            return info
    
    def delete(self, token: str) -> None:
        with self._lock:
            self._store.pop(token, None)
    
    def increment_downloads(self, token: str) -> int:
        with self._lock:
            info = self._store.get(token)
            if info:
                info.download_count += 1
                return info.download_count
            return 0


class RedisTokenStore(TokenStore):
    """Redis Token存储（生产环境推荐）"""
    
    def __init__(self, redis_client, prefix: str = "storage:token:"):
        self.redis = redis_client
        self.prefix = prefix
    
    def _key(self, token: str) -> str:
        return f"{self.prefix}{token}"
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        import json
        data = {
            'file_path': info.file_path,
            'expires_at': info.expires_at.isoformat(),
            'user_id': info.user_id,
            'download': info.download,
            'filename': info.filename,
            'max_downloads': info.max_downloads,
            'download_count': info.download_count,
            'metadata': info.metadata,
        }
        self.redis.setex(self._key(token), ttl, json.dumps(data))
    
    def get(self, token: str) -> Optional[TokenInfo]:
        import json
        data = self.redis.get(self._key(token))
        if not data:
            return None
        
        data = json.loads(data)
        return TokenInfo(
            file_path=data['file_path'],
            expires_at=datetime.fromisoformat(data['expires_at']),
            user_id=data.get('user_id'),
            download=data.get('download', False),
            filename=data.get('filename'),
            max_downloads=data.get('max_downloads'),
            download_count=data.get('download_count', 0),
            metadata=data.get('metadata'),
        )
    
    def delete(self, token: str) -> None:
        self.redis.delete(self._key(token))
    
    def increment_downloads(self, token: str) -> int:
        # 使用 Lua 脚本保证原子性
        script = """
        local data = redis.call('GET', KEYS[1])
        if not data then return -1 end
        local obj = cjson.decode(data)
        obj.download_count = (obj.download_count or 0) + 1
        redis.call('SET', KEYS[1], cjson.encode(obj), 'KEEPTTL')
        return obj.download_count
        """
        return self.redis.eval(script, 1, self._key(token))


class SecureURLGenerator:
    """安全URL生成器
    
    提供两种安全访问机制：
    1. Token访问：生成随机Token，信息存储在服务端
    2. 签名URL：使用HMAC签名，无需服务端存储
    
    使用示例:
        # 初始化
        generator = SecureURLGenerator(
            secret_key="your-secret-key",
            base_url="/api/files",
            token_store=RedisTokenStore(redis_client),  # 生产环境
        )
        
        # 生成Token访问URL（需要验证用户）
        url = generator.generate(
            file_path="private/report.pdf",
            expires_in=3600,
            user_id=current_user.id,
            download=True,
            filename="报告.pdf"
        )
        
        # 生成签名URL（可分享）
        url = generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=86400
        )
    """
    
    def __init__(
        self,
        secret_key: str,
        base_url: str = "/api/files",
        token_store: Optional[TokenStore] = None,
    ):
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.token_store = token_store or MemoryTokenStore()
    
    def generate(
        self,
        file_path: str,
        expires_in: int = 3600,
        user_id: Optional[int] = None,
        download: bool = False,
        filename: Optional[str] = None,
        max_downloads: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SecureURL:
        """生成Token访问URL
        
        Args:
            file_path: 文件路径
            expires_in: 过期时间（秒）
            user_id: 限制访问的用户ID
            download: 是否强制下载
            filename: 下载时的文件名
            max_downloads: 最大下载次数
            metadata: 附加元数据
            
        Returns:
            SecureURL: 安全URL对象
        """
        # 生成随机Token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # 存储Token信息
        info = TokenInfo(
            file_path=file_path,
            expires_at=expires_at,
            user_id=user_id,
            download=download,
            filename=filename,
            max_downloads=max_downloads,
            download_count=0,
            metadata=metadata or {},
        )
        self.token_store.set(token, info, expires_in)
        
        # 构建URL
        url = f"{self.base_url}/t/{token}"
        
        return SecureURL(
            url=url,
            token=token,
            expires_at=expires_at,
            file_path=file_path,
        )
    
    def generate_signed(
        self,
        file_path: str,
        expires_in: int = 3600,
    ) -> str:
        """生成签名URL（无需服务端存储）
        
        Args:
            file_path: 文件路径
            expires_in: 过期时间（秒）
            
        Returns:
            str: 签名URL
        """
        expires = int((datetime.now() + timedelta(seconds=expires_in)).timestamp())
        
        # 生成签名
        sign_str = f"{file_path}:{expires}"
        signature = hmac.new(
            self.secret_key.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()[:24]
        
        # 编码路径（Base64 URL安全编码）
        encoded_path = base64.urlsafe_b64encode(file_path.encode()).decode().rstrip('=')
        
        return f"{self.base_url}/s/{encoded_path}?e={expires}&s={signature}"
    
    def validate_token(
        self,
        token: str,
        user_id: Optional[int] = None,
    ) -> Optional[TokenInfo]:
        """验证Token
        
        Args:
            token: 访问Token
            user_id: 当前用户ID（用于验证用户限制）
            
        Returns:
            TokenInfo: 验证通过返回Token信息，否则返回None
        """
        info = self.token_store.get(token)
        if not info:
            logger.debug(f"Token不存在或已过期: {token[:8]}...")
            return None
        
        # 检查过期（双重检查）
        if datetime.now() > info.expires_at:
            self.token_store.delete(token)
            return None
        
        # 检查用户限制
        if info.user_id is not None and info.user_id != user_id:
            logger.warning(f"用户ID不匹配: expected={info.user_id}, actual={user_id}")
            return None
        
        # 检查下载次数
        if info.max_downloads is not None:
            count = self.token_store.increment_downloads(token)
            if count > info.max_downloads:
                logger.debug(f"超过最大下载次数: {count}/{info.max_downloads}")
                self.token_store.delete(token)
                return None
            info.download_count = count
        
        return info
    
    def validate_signed(
        self,
        encoded_path: str,
        expires: int,
        signature: str,
    ) -> Optional[str]:
        """验证签名URL
        
        Args:
            encoded_path: Base64编码的文件路径
            expires: 过期时间戳
            signature: 签名
            
        Returns:
            str: 验证通过返回文件路径，否则返回None
        """
        # 检查过期
        if datetime.now().timestamp() > expires:
            return None
        
        # 解码路径（处理缺失的padding）
        padding = 4 - len(encoded_path) % 4
        if padding != 4:
            encoded_path += '=' * padding
        
        try:
            file_path = base64.urlsafe_b64decode(encoded_path).decode()
        except Exception:
            return None
        
        # 验证签名
        sign_str = f"{file_path}:{expires}"
        expected_sig = hmac.new(
            self.secret_key.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()[:24]
        
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning(f"签名验证失败: {file_path}")
            return None
        
        return file_path
    
    def revoke(self, token: str) -> None:
        """撤销Token"""
        self.token_store.delete(token)
```

### 3.5 FastAPI 集成 (integrations/fastapi.py)

```python
from typing import Optional, Callable
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, Response
import logging

from ..manager import StorageManager
from ..secure_url import SecureURLGenerator
from ..exceptions import StorageError

logger = logging.getLogger(__name__)


def create_storage_router(
    secure_url_generator: SecureURLGenerator,
    get_current_user: Optional[Callable] = None,
    prefix: str = "/api/files",
    tags: list = None,
) -> APIRouter:
    """创建文件访问路由
    
    Args:
        secure_url_generator: 安全URL生成器
        get_current_user: 获取当前用户的依赖函数（可选）
        prefix: 路由前缀
        tags: OpenAPI标签
        
    Returns:
        APIRouter: FastAPI路由
        
    使用示例:
        from yweb.storage.integrations.fastapi import create_storage_router
        
        router = create_storage_router(
            secure_url_generator=secure_url,
            get_current_user=get_current_user_optional,
        )
        app.include_router(router)
    """
    router = APIRouter(prefix=prefix, tags=tags or ["files"])
    
    async def get_user_id(request: Request) -> Optional[int]:
        """获取当前用户ID"""
        if not get_current_user:
            return None
        try:
            user = await get_current_user(request)
            return user.id if user else None
        except Exception:
            return None
    
    @router.get("/t/{token}")
    async def get_file_by_token(
        token: str,
        request: Request,
    ):
        """通过Token访问文件
        
        - Token可能限制特定用户访问
        - Token可能限制下载次数
        - Token有过期时间
        """
        user_id = await get_user_id(request)
        
        # 验证Token
        info = secure_url_generator.validate_token(token, user_id)
        if not info:
            raise HTTPException(404, "文件不存在或链接已过期")
        
        # 获取文件
        try:
            storage = StorageManager.get()
            content = storage.read(info.file_path)
            file_info = storage.get_info(info.file_path)
        except FileNotFoundError:
            raise HTTPException(404, "文件不存在")
        except StorageError as e:
            logger.error(f"读取文件失败: {e}")
            raise HTTPException(500, "文件读取失败")
        
        # 构建响应头
        headers = {}
        if info.download:
            filename = info.filename or file_info.filename
            # 处理中文文件名
            try:
                filename.encode('ascii')
                headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            except UnicodeEncodeError:
                from urllib.parse import quote
                headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
        
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        return StreamingResponse(
            content,
            media_type=file_info.content_type or 'application/octet-stream',
            headers=headers,
        )
    
    @router.get("/s/{encoded_path:path}")
    async def get_file_by_signature(
        encoded_path: str,
        e: int = Query(..., description="过期时间戳"),
        s: str = Query(..., description="签名"),
    ):
        """通过签名URL访问文件
        
        - 签名URL可公开分享
        - 不需要登录
        - 有过期时间
        """
        # 验证签名
        file_path = secure_url_generator.validate_signed(encoded_path, e, s)
        if not file_path:
            raise HTTPException(404, "链接无效或已过期")
        
        # 获取文件
        try:
            storage = StorageManager.get()
            content = storage.read(file_path)
            file_info = storage.get_info(file_path)
        except FileNotFoundError:
            raise HTTPException(404, "文件不存在")
        except StorageError as e:
            logger.error(f"读取文件失败: {e}")
            raise HTTPException(500, "文件读取失败")
        
        headers = {}
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        return StreamingResponse(
            content,
            media_type=file_info.content_type or 'application/octet-stream',
            headers=headers,
        )
    
    @router.head("/t/{token}")
    async def head_file_by_token(token: str, request: Request):
        """获取文件元信息（Token方式）"""
        user_id = await get_user_id(request)
        
        info = secure_url_generator.validate_token(token, user_id)
        if not info:
            raise HTTPException(404, "文件不存在或链接已过期")
        
        try:
            storage = StorageManager.get()
            file_info = storage.get_info(info.file_path)
        except FileNotFoundError:
            raise HTTPException(404, "文件不存在")
        
        headers = {
            'Content-Length': str(file_info.size),
            'Content-Type': file_info.content_type or 'application/octet-stream',
        }
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        return Response(headers=headers)
    
    return router
```

---

## 4. 使用指南

### 4.1 基本使用

```python
from yweb.storage import StorageManager, MemoryStorage, LocalStorage

# 初始化存储后端
StorageManager.register('temp', MemoryStorage(max_size=50*1024*1024))
StorageManager.register('local', LocalStorage('/data/uploads'), default=True)

# 保存文件
storage = StorageManager.get()
storage.save('images/avatar.jpg', file_content, content_type='image/jpeg')

# 读取文件
content = storage.read('images/avatar.jpg')
data = content.read()

# 删除文件
storage.delete('images/avatar.jpg')

# 检查文件存在
if storage.exists('images/avatar.jpg'):
    info = storage.get_info('images/avatar.jpg')
    print(f"文件大小: {info.size}")
```

### 4.2 安全访问

```python
from yweb.storage import SecureURLGenerator, RedisTokenStore
import redis

# 初始化（生产环境使用 Redis）
redis_client = redis.Redis(host='localhost', port=6379, db=0)
secure_url = SecureURLGenerator(
    secret_key="your-secret-key-at-least-32-chars",
    base_url="/api/files",
    token_store=RedisTokenStore(redis_client),
)

# 生成需要登录的文件链接
url = secure_url.generate(
    file_path="private/reports/2024-q1.pdf",
    expires_in=3600,           # 1小时后过期
    user_id=current_user.id,   # 限制只有该用户能访问
    download=True,
    filename="Q1季度报告.pdf",
    max_downloads=3,           # 最多下载3次
)
print(url.url)  # /api/files/t/abc123...

# 生成可分享的签名链接（无需登录）
public_url = secure_url.generate_signed(
    file_path="public/images/banner.jpg",
    expires_in=86400,  # 24小时
)
print(public_url)  # /api/files/s/cHVibGljL2ltYWdlcy9iYW5uZXIuanBn?e=1706000000&s=a1b2c3d4
```

### 4.3 FastAPI 集成

```python
from fastapi import FastAPI
from yweb.storage import StorageManager, LocalStorage, SecureURLGenerator
from yweb.storage.integrations.fastapi import create_storage_router

app = FastAPI()

# 初始化存储
StorageManager.register('local', LocalStorage('/data/uploads'), default=True)

# 初始化安全URL生成器
secure_url = SecureURLGenerator(
    secret_key="your-secret-key",
    base_url="/api/files",
)

# 注册路由
router = create_storage_router(
    secure_url_generator=secure_url,
    get_current_user=get_current_user_optional,  # 你的用户认证函数
)
app.include_router(router)

# 上传接口
@app.post("/upload")
async def upload_file(file: UploadFile, current_user = Depends(get_current_user)):
    storage = StorageManager.get()
    
    # 生成唯一路径
    path = f"uploads/{current_user.id}/{uuid4()}/{file.filename}"
    
    # 保存文件
    storage.save(path, file.file, content_type=file.content_type)
    
    # 生成安全访问URL
    url = secure_url.generate(
        file_path=path,
        expires_in=86400,
        user_id=current_user.id,
    )
    
    return {"url": url.url, "expires_at": url.expires_at}
```

### 4.4 配置文件初始化

```python
# config.py
STORAGE_CONFIG = {
    'temp': {
        'type': 'memory',
        'max_size': 50 * 1024 * 1024,  # 50MB
    },
    'local': {
        'type': 'local',
        'base_path': '/data/uploads',
    },
    'oss': {
        'type': 'oss',
        'access_key_id': 'your-key-id',
        'access_key_secret': 'your-key-secret',
        'endpoint': 'oss-cn-hangzhou.aliyuncs.com',
        'bucket_name': 'your-bucket',
        'prefix': 'uploads/',
    },
    'default': 'oss',  # 设置默认后端
}

# main.py
from yweb.storage import StorageManager
from config import STORAGE_CONFIG

StorageManager.configure(STORAGE_CONFIG)
```

---

## 5. 实现计划

### 5.1 阶段划分

| 阶段 | 内容 | 优先级 | 预估工作量 |
|------|------|--------|-----------|
| **Phase 1** | 核心框架 | P0 | |
| | - 抽象基类定义 | | |
| | - 内存存储实现 | | |
| | - 本地存储实现 | | |
| | - 存储管理器 | | |
| | - 基础单元测试 | | |
| **Phase 2** | 安全访问 | P0 | |
| | - SecureURLGenerator | | |
| | - Token存储（内存） | | |
| | - 签名URL | | |
| | - FastAPI路由集成 | | |
| **Phase 3** | 云存储 | P1 | |
| | - 阿里云OSS后端 | | |
| | - AWS S3后端 | | |
| | - MinIO支持 | | |
| **Phase 4** | 生产增强 | P1 | |
| | - Redis Token存储 | | |
| | - 文件类型验证 | | |
| | - 大文件分片上传 | | |
| **Phase 5** | 高级功能 | P2 | |
| | - 异步支持 | | |
| | - 图片处理集成 | | |
| | - FTP/SFTP后端 | | |

### 5.2 依赖说明

| 后端 | 依赖包 | 安装命令 |
|------|--------|---------|
| 内存/本地 | 无 | — |
| 阿里云OSS | oss2 | `pip install oss2` |
| AWS S3 | boto3 | `pip install boto3` |
| Redis Token | redis | `pip install redis` |

---

## 6. 安全考虑

### 6.1 路径安全

- **路径穿越防护**：所有路径操作前验证，确保不会访问基础路径外的文件
- **文件名过滤**：过滤危险字符（`..`, `/`, `\`）

### 6.2 访问控制

- **Token机制**：支持用户绑定、下载次数限制、过期时间
- **签名URL**：使用HMAC-SHA256签名，防止篡改

### 6.3 密钥管理

- **Secret Key**：至少32字符，从环境变量读取
- **云存储凭证**：使用环境变量或密钥管理服务

### 6.4 建议配置

```python
# 安全配置示例
STORAGE_SECRET_KEY = os.environ['STORAGE_SECRET_KEY']  # 从环境变量读取
TOKEN_DEFAULT_EXPIRES = 3600  # 默认1小时过期
TOKEN_MAX_EXPIRES = 86400 * 7  # 最长7天
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'}
```

---

## 7. 附录

### 7.1 异常定义

```python
# exceptions.py

class StorageError(Exception):
    """存储操作错误基类"""
    pass

class StorageConfigError(StorageError):
    """配置错误"""
    pass

class StorageQuotaExceeded(StorageError):
    """存储配额超限"""
    pass

class InvalidFileType(StorageError):
    """无效的文件类型"""
    pass
```

### 7.2 公共API导出

```python
# __init__.py

from .base import StorageBackend, FileInfo
from .manager import StorageManager
from .secure_url import SecureURLGenerator, SecureURL, TokenStore, MemoryTokenStore
from .exceptions import StorageError, StorageConfigError, StorageQuotaExceeded

from .backends.memory import MemoryStorage
from .backends.local import LocalStorage

__all__ = [
    # 基类
    'StorageBackend',
    'FileInfo',
    
    # 管理器
    'StorageManager',
    
    # 安全URL
    'SecureURLGenerator',
    'SecureURL',
    'TokenStore',
    'MemoryTokenStore',
    
    # 后端
    'MemoryStorage',
    'LocalStorage',
    
    # 异常
    'StorageError',
    'StorageConfigError',
    'StorageQuotaExceeded',
]

# 延迟导入可选后端
def __getattr__(name):
    if name == 'OSSStorage':
        from .backends.oss import OSSStorage
        return OSSStorage
    if name == 'S3Storage':
        from .backends.s3 import S3Storage
        return S3Storage
    if name == 'RedisTokenStore':
        from .secure_url import RedisTokenStore
        return RedisTokenStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

---

## 8. 改进方案

### 8.1 同步/异步双模式支持

**问题**：所有接口都是同步的，对于网络存储（OSS、S3）可能阻塞事件循环

**解决方案**：提供同步和异步两套接口

```python
# base.py - 异步抽象基类

from abc import ABC, abstractmethod
from typing import AsyncIterator

class AsyncStorageBackend(ABC):
    """异步存储后端抽象基类"""
    
    @abstractmethod
    async def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes, AsyncIterator[bytes]],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """异步保存文件"""
        pass
    
    @abstractmethod
    async def read(self, path: str) -> AsyncIterator[bytes]:
        """异步读取文件，返回异步迭代器"""
        pass
    
    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """异步读取文件内容为字节"""
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """异步删除文件"""
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """异步检查文件是否存在"""
        pass
    
    @abstractmethod
    async def get_info(self, path: str) -> FileInfo:
        """异步获取文件信息"""
        pass
    
    @abstractmethod
    async def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """异步列出文件"""
        pass


# backends/local_async.py - 异步本地存储实现

import aiofiles
import aiofiles.os
from pathlib import Path

class AsyncLocalStorage(AsyncStorageBackend):
    """异步本地文件系统存储"""
    
    def __init__(self, base_path: str, **kwargs):
        self.base_path = Path(base_path).resolve()
    
    async def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes, AsyncIterator[bytes]],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        full_path = self._resolve_path(path)
        
        # 检查是否已存在
        if not overwrite and await aiofiles.os.path.exists(full_path):
            raise FileExistsError(f"文件已存在: {path}")
        
        # 创建目录
        await aiofiles.os.makedirs(full_path.parent, exist_ok=True)
        
        # 写入文件
        async with aiofiles.open(full_path, 'wb') as f:
            if isinstance(content, bytes):
                await f.write(content)
            elif hasattr(content, '__aiter__'):
                # 异步迭代器
                async for chunk in content:
                    await f.write(chunk)
            else:
                # 同步文件对象，在线程池中读取
                import asyncio
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, content.read)
                await f.write(data)
        
        return path
    
    async def read(self, path: str) -> AsyncIterator[bytes]:
        full_path = self._resolve_path(path)
        
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"文件不存在: {path}")
        
        async def _stream():
            async with aiofiles.open(full_path, 'rb') as f:
                while chunk := await f.read(65536):  # 64KB chunks
                    yield chunk
        
        return _stream()
    
    async def read_bytes(self, path: str) -> bytes:
        full_path = self._resolve_path(path)
        
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"文件不存在: {path}")
        
        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()


# backends/oss_async.py - 异步OSS存储

class AsyncOSSStorage(AsyncStorageBackend):
    """异步阿里云 OSS 存储
    
    依赖: pip install oss2 aiohttp
    
    注意：oss2 SDK 本身是同步的，这里通过线程池实现异步
    """
    
    def __init__(self, **kwargs):
        # 同步后端用于线程池执行
        self._sync_backend = OSSStorage(**kwargs)
    
    async def save(self, path: str, content: Union[BinaryIO, bytes], **kwargs) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync_backend.save(path, content, **kwargs)
        )
    
    async def read_bytes(self, path: str) -> bytes:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync_backend.read_bytes(path)
        )
    
    # ... 其他方法类似


# 同步包装器 - 让同步后端支持异步接口

class SyncToAsyncAdapter(AsyncStorageBackend):
    """将同步后端适配为异步接口"""
    
    def __init__(self, sync_backend: StorageBackend, executor=None):
        self._sync = sync_backend
        self._executor = executor  # 可指定自定义线程池
    
    async def save(self, path: str, content, **kwargs) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._sync.save(path, content, **kwargs)
        )
    
    # ... 其他方法类似
```

**使用示例**：

```python
# 同步使用
storage = LocalStorage('/data/uploads')
storage.save('file.txt', b'content')

# 异步使用
async_storage = AsyncLocalStorage('/data/uploads')
await async_storage.save('file.txt', b'content')

# 同步后端适配为异步
async_storage = SyncToAsyncAdapter(OSSStorage(...))
await async_storage.save('file.txt', b'content')
```

### 8.2 文件验证机制

**问题**：上传文件时缺少格式、大小等验证

**解决方案**：添加可配置的验证器

```python
# validators.py

from dataclasses import dataclass, field
from typing import Set, Optional, Callable, List
import magic  # python-magic 库
import hashlib

@dataclass
class FileValidationConfig:
    """文件验证配置"""
    
    # 大小限制
    max_size: Optional[int] = None          # 最大文件大小（字节）
    min_size: int = 0                        # 最小文件大小
    
    # 类型限制
    allowed_extensions: Set[str] = field(default_factory=set)  # 允许的扩展名 {'.jpg', '.png'}
    blocked_extensions: Set[str] = field(default_factory=set)  # 禁止的扩展名 {'.exe', '.sh'}
    allowed_mimes: Set[str] = field(default_factory=set)       # 允许的MIME类型
    blocked_mimes: Set[str] = field(default_factory=set)       # 禁止的MIME类型
    
    # 内容验证
    verify_magic: bool = True               # 验证文件魔数（防止伪造扩展名）
    scan_virus: bool = False                # 病毒扫描（需要外部服务）
    
    # 图片特定验证
    image_max_width: Optional[int] = None
    image_max_height: Optional[int] = None
    image_max_pixels: Optional[int] = None  # 防止解压炸弹
    
    # 自定义验证器
    custom_validators: List[Callable] = field(default_factory=list)


class FileValidator:
    """文件验证器"""
    
    # 预定义配置
    PRESETS = {
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
    }
    
    def __init__(self, config: Optional[FileValidationConfig] = None, preset: Optional[str] = None):
        if preset:
            self.config = self.PRESETS.get(preset, FileValidationConfig())
        else:
            self.config = config or FileValidationConfig()
    
    def validate(
        self,
        content: Union[bytes, BinaryIO],
        filename: str,
        content_type: Optional[str] = None,
    ) -> 'ValidationResult':
        """验证文件
        
        Args:
            content: 文件内容
            filename: 文件名
            content_type: 上传时声明的MIME类型
            
        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        warnings = []
        
        # 读取内容
        if isinstance(content, bytes):
            data = content
        else:
            pos = content.tell()
            data = content.read()
            content.seek(pos)
        
        # 1. 大小验证
        size = len(data)
        if self.config.max_size and size > self.config.max_size:
            errors.append(f"文件大小 {size} 超过限制 {self.config.max_size}")
        if size < self.config.min_size:
            errors.append(f"文件大小 {size} 小于最小要求 {self.config.min_size}")
        
        # 2. 扩展名验证
        ext = self._get_extension(filename).lower()
        if self.config.allowed_extensions and ext not in self.config.allowed_extensions:
            errors.append(f"不允许的文件扩展名: {ext}")
        if ext in self.config.blocked_extensions:
            errors.append(f"禁止的文件扩展名: {ext}")
        
        # 3. MIME类型验证（声明的类型）
        if content_type:
            if self.config.allowed_mimes and content_type not in self.config.allowed_mimes:
                warnings.append(f"声明的MIME类型不在允许列表: {content_type}")
            if content_type in self.config.blocked_mimes:
                errors.append(f"禁止的MIME类型: {content_type}")
        
        # 4. 魔数验证（实际类型）
        if self.config.verify_magic:
            try:
                actual_mime = magic.from_buffer(data[:2048], mime=True)
                
                # 检查扩展名与实际类型是否匹配
                if not self._mime_matches_extension(actual_mime, ext):
                    warnings.append(f"文件扩展名 {ext} 与实际类型 {actual_mime} 不匹配")
                
                # 检查实际类型是否允许
                if self.config.allowed_mimes and actual_mime not in self.config.allowed_mimes:
                    errors.append(f"实际文件类型不允许: {actual_mime}")
                if actual_mime in self.config.blocked_mimes:
                    errors.append(f"禁止的实际文件类型: {actual_mime}")
                    
            except Exception as e:
                warnings.append(f"无法检测文件类型: {e}")
        
        # 5. 图片特定验证
        if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}:
            img_errors = self._validate_image(data)
            errors.extend(img_errors)
        
        # 6. 自定义验证器
        for validator in self.config.custom_validators:
            try:
                result = validator(data, filename, content_type)
                if isinstance(result, str):
                    errors.append(result)
                elif result is False:
                    errors.append("自定义验证失败")
            except Exception as e:
                errors.append(f"自定义验证异常: {e}")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            size=size,
            detected_mime=actual_mime if self.config.verify_magic else None,
        )
    
    def _get_extension(self, filename: str) -> str:
        """获取文件扩展名"""
        if '.' in filename:
            return '.' + filename.rsplit('.', 1)[-1]
        return ''
    
    def _mime_matches_extension(self, mime: str, ext: str) -> bool:
        """检查MIME类型与扩展名是否匹配"""
        MIME_EXT_MAP = {
            'image/jpeg': {'.jpg', '.jpeg'},
            'image/png': {'.png'},
            'image/gif': {'.gif'},
            'image/webp': {'.webp'},
            'application/pdf': {'.pdf'},
            'application/msword': {'.doc'},
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'.docx'},
            # ... 更多映射
        }
        expected_exts = MIME_EXT_MAP.get(mime, set())
        return not expected_exts or ext in expected_exts
    
    def _validate_image(self, data: bytes) -> List[str]:
        """验证图片"""
        errors = []
        try:
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(data))
            width, height = img.size
            pixels = width * height
            
            if self.config.image_max_width and width > self.config.image_max_width:
                errors.append(f"图片宽度 {width} 超过限制 {self.config.image_max_width}")
            
            if self.config.image_max_height and height > self.config.image_max_height:
                errors.append(f"图片高度 {height} 超过限制 {self.config.image_max_height}")
            
            if self.config.image_max_pixels and pixels > self.config.image_max_pixels:
                errors.append(f"图片像素数 {pixels} 超过限制 {self.config.image_max_pixels}")
                
        except Exception as e:
            errors.append(f"图片验证失败: {e}")
        
        return errors


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool                    # 是否通过验证
    errors: List[str]              # 错误列表
    warnings: List[str]            # 警告列表
    size: int                      # 文件大小
    detected_mime: Optional[str]   # 检测到的MIME类型
```

**集成到存储后端**：

```python
class ValidatedStorageMixin:
    """带验证功能的存储Mixin"""
    
    def __init__(self, *args, validator: Optional[FileValidator] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.validator = validator
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        validate: bool = True,
        **kwargs
    ) -> str:
        # 验证文件
        if validate and self.validator:
            result = self.validator.validate(content, path, content_type)
            if not result.valid:
                raise InvalidFileError(result.errors)
            
            # 使用检测到的MIME类型
            if result.detected_mime and not content_type:
                content_type = result.detected_mime
        
        return super().save(path, content, content_type=content_type, **kwargs)


class ValidatedLocalStorage(ValidatedStorageMixin, LocalStorage):
    """带验证的本地存储"""
    pass


# 使用
storage = ValidatedLocalStorage(
    '/data/uploads',
    validator=FileValidator(preset='image')
)
storage.save('avatar.jpg', file_content)  # 自动验证
```

### 8.3 分片上传支持

**问题**：大文件上传需要完整读入内存

**解决方案**：添加分片上传接口

```python
# multipart.py

from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import hashlib
import uuid

@dataclass
class UploadPart:
    """上传分片"""
    part_number: int          # 分片序号（从1开始）
    etag: str                 # 分片ETag
    size: int                 # 分片大小


@dataclass
class MultipartUpload:
    """分片上传任务"""
    upload_id: str            # 上传ID
    path: str                 # 目标路径
    created_at: datetime      # 创建时间
    expires_at: datetime      # 过期时间
    parts: List[UploadPart]   # 已上传的分片


class MultipartUploadMixin:
    """分片上传Mixin
    
    为存储后端添加分片上传能力
    """
    
    def __init__(self, *args, multipart_store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._multipart_store = multipart_store or {}  # 生产环境应使用Redis
    
    def init_multipart_upload(
        self,
        path: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        expires_in: int = 86400,  # 默认24小时
    ) -> str:
        """初始化分片上传
        
        Args:
            path: 目标文件路径
            content_type: MIME类型
            metadata: 元数据
            expires_in: 上传任务过期时间（秒）
            
        Returns:
            str: 上传ID
        """
        upload_id = str(uuid.uuid4())
        
        self._multipart_store[upload_id] = MultipartUpload(
            upload_id=upload_id,
            path=path,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=expires_in),
            parts=[],
        )
        
        return upload_id
    
    def upload_part(
        self,
        upload_id: str,
        part_number: int,
        content: bytes,
    ) -> UploadPart:
        """上传分片
        
        Args:
            upload_id: 上传ID
            part_number: 分片序号（1-10000）
            content: 分片内容
            
        Returns:
            UploadPart: 分片信息
        """
        upload = self._get_upload(upload_id)
        
        if not 1 <= part_number <= 10000:
            raise ValueError("分片序号必须在 1-10000 之间")
        
        # 计算 ETag
        etag = hashlib.md5(content).hexdigest()
        
        # 存储分片（临时文件）
        part_path = f"_multipart/{upload_id}/{part_number}"
        super().save(part_path, content)
        
        # 记录分片
        part = UploadPart(
            part_number=part_number,
            etag=etag,
            size=len(content),
        )
        
        # 更新或添加分片记录
        existing = [p for p in upload.parts if p.part_number == part_number]
        if existing:
            upload.parts.remove(existing[0])
        upload.parts.append(part)
        upload.parts.sort(key=lambda p: p.part_number)
        
        return part
    
    def complete_multipart_upload(
        self,
        upload_id: str,
        parts: Optional[List[dict]] = None,  # [{'part_number': 1, 'etag': '...'}, ...]
    ) -> str:
        """完成分片上传
        
        Args:
            upload_id: 上传ID
            parts: 分片列表（可选，用于验证）
            
        Returns:
            str: 最终文件路径
        """
        upload = self._get_upload(upload_id)
        
        if not upload.parts:
            raise ValueError("没有上传任何分片")
        
        # 验证分片
        if parts:
            for p in parts:
                uploaded = next(
                    (up for up in upload.parts if up.part_number == p['part_number']),
                    None
                )
                if not uploaded or uploaded.etag != p['etag']:
                    raise ValueError(f"分片 {p['part_number']} 验证失败")
        
        # 合并分片
        merged_content = b''
        for part in sorted(upload.parts, key=lambda p: p.part_number):
            part_path = f"_multipart/{upload_id}/{part.part_number}"
            merged_content += super().read_bytes(part_path)
        
        # 保存最终文件
        result = super().save(upload.path, merged_content)
        
        # 清理临时文件和上传记录
        self._cleanup_upload(upload_id)
        
        return result
    
    def abort_multipart_upload(self, upload_id: str) -> bool:
        """取消分片上传"""
        try:
            self._cleanup_upload(upload_id)
            return True
        except Exception:
            return False
    
    def list_parts(self, upload_id: str) -> List[UploadPart]:
        """列出已上传的分片"""
        upload = self._get_upload(upload_id)
        return upload.parts
    
    def _get_upload(self, upload_id: str) -> MultipartUpload:
        """获取上传任务"""
        upload = self._multipart_store.get(upload_id)
        if not upload:
            raise ValueError(f"上传任务不存在: {upload_id}")
        if datetime.now() > upload.expires_at:
            self._cleanup_upload(upload_id)
            raise ValueError(f"上传任务已过期: {upload_id}")
        return upload
    
    def _cleanup_upload(self, upload_id: str):
        """清理上传任务"""
        # 删除临时分片
        try:
            for part in self._multipart_store[upload_id].parts:
                part_path = f"_multipart/{upload_id}/{part.part_number}"
                super().delete(part_path)
        except Exception:
            pass
        
        # 删除记录
        self._multipart_store.pop(upload_id, None)


# 使用
class MultipartLocalStorage(MultipartUploadMixin, LocalStorage):
    """支持分片上传的本地存储"""
    pass
```

**FastAPI 分片上传端点**：

```python
# integrations/fastapi_multipart.py

@router.post("/multipart/init")
async def init_multipart(
    path: str,
    content_type: Optional[str] = None,
    current_user = Depends(get_current_user),
):
    """初始化分片上传"""
    storage = StorageManager.get()
    upload_id = storage.init_multipart_upload(path, content_type)
    return {"upload_id": upload_id}


@router.put("/multipart/{upload_id}/parts/{part_number}")
async def upload_part(
    upload_id: str,
    part_number: int,
    file: UploadFile,
    current_user = Depends(get_current_user),
):
    """上传分片"""
    storage = StorageManager.get()
    content = await file.read()
    part = storage.upload_part(upload_id, part_number, content)
    return {"part_number": part.part_number, "etag": part.etag}


@router.post("/multipart/{upload_id}/complete")
async def complete_multipart(
    upload_id: str,
    parts: List[dict] = Body(...),  # [{"part_number": 1, "etag": "..."}]
    current_user = Depends(get_current_user),
):
    """完成分片上传"""
    storage = StorageManager.get()
    path = storage.complete_multipart_upload(upload_id, parts)
    return {"path": path}


@router.delete("/multipart/{upload_id}")
async def abort_multipart(
    upload_id: str,
    current_user = Depends(get_current_user),
):
    """取消分片上传"""
    storage = StorageManager.get()
    storage.abort_multipart_upload(upload_id)
    return {"status": "aborted"}
```

### 8.4 监控和日志增强

**问题**：缺少操作统计、性能指标

**解决方案**：添加指标收集和结构化日志

```python
# metrics.py

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from contextlib import contextmanager
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OperationType(Enum):
    SAVE = "save"
    READ = "read"
    DELETE = "delete"
    LIST = "list"
    EXISTS = "exists"
    GET_INFO = "get_info"
    GET_URL = "get_url"


@dataclass
class OperationMetrics:
    """操作指标"""
    count: int = 0                    # 操作次数
    success_count: int = 0            # 成功次数
    error_count: int = 0              # 错误次数
    total_bytes: int = 0              # 总字节数
    total_duration_ms: float = 0      # 总耗时（毫秒）
    
    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.count if self.count else 0
    
    @property
    def success_rate(self) -> float:
        return self.success_count / self.count if self.count else 0


@dataclass  
class StorageMetrics:
    """存储指标"""
    backend_name: str
    operations: Dict[str, OperationMetrics] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    
    def record(
        self,
        operation: OperationType,
        success: bool,
        duration_ms: float,
        bytes_count: int = 0,
    ):
        """记录操作"""
        op_name = operation.value
        if op_name not in self.operations:
            self.operations[op_name] = OperationMetrics()
        
        metrics = self.operations[op_name]
        metrics.count += 1
        if success:
            metrics.success_count += 1
        else:
            metrics.error_count += 1
        metrics.total_bytes += bytes_count
        metrics.total_duration_ms += duration_ms
    
    def to_dict(self) -> dict:
        """转换为字典"""
        uptime = time.time() - self.start_time
        return {
            'backend': self.backend_name,
            'uptime_seconds': uptime,
            'operations': {
                name: {
                    'count': m.count,
                    'success_count': m.success_count,
                    'error_count': m.error_count,
                    'success_rate': f"{m.success_rate:.2%}",
                    'total_bytes': m.total_bytes,
                    'avg_duration_ms': f"{m.avg_duration_ms:.2f}",
                }
                for name, m in self.operations.items()
            }
        }


class MetricsCollector:
    """指标收集器（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._metrics: Dict[str, StorageMetrics] = {}
                    cls._instance._callbacks: list = []
        return cls._instance
    
    def get_or_create(self, backend_name: str) -> StorageMetrics:
        """获取或创建后端指标"""
        if backend_name not in self._metrics:
            self._metrics[backend_name] = StorageMetrics(backend_name)
        return self._metrics[backend_name]
    
    def get_all(self) -> Dict[str, dict]:
        """获取所有指标"""
        return {name: m.to_dict() for name, m in self._metrics.items()}
    
    def on_operation(self, callback: Callable):
        """注册操作回调（用于推送到外部监控系统）"""
        self._callbacks.append(callback)
    
    def notify(self, backend: str, operation: str, success: bool, duration: float, **extra):
        """通知回调"""
        for callback in self._callbacks:
            try:
                callback(backend, operation, success, duration, **extra)
            except Exception:
                pass


class InstrumentedStorageMixin:
    """带指标收集的存储Mixin"""
    
    def __init__(self, *args, metrics_name: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._metrics_name = metrics_name or self.__class__.__name__
        self._collector = MetricsCollector()
        self._metrics = self._collector.get_or_create(self._metrics_name)
    
    @contextmanager
    def _track_operation(self, operation: OperationType, path: str = "", size: int = 0):
        """跟踪操作"""
        start = time.perf_counter()
        success = True
        error = None
        
        try:
            yield
        except Exception as e:
            success = False
            error = e
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self._metrics.record(operation, success, duration_ms, size)
            
            # 结构化日志
            log_data = {
                'backend': self._metrics_name,
                'operation': operation.value,
                'path': path,
                'success': success,
                'duration_ms': f"{duration_ms:.2f}",
            }
            if size:
                log_data['bytes'] = size
            if error:
                log_data['error'] = str(error)
            
            if success:
                logger.info(f"Storage operation completed", extra=log_data)
            else:
                logger.error(f"Storage operation failed", extra=log_data)
            
            # 通知外部监控
            self._collector.notify(
                self._metrics_name,
                operation.value,
                success,
                duration_ms,
                path=path,
                size=size,
            )
    
    def save(self, path: str, content, **kwargs) -> str:
        size = len(content) if isinstance(content, bytes) else 0
        with self._track_operation(OperationType.SAVE, path, size):
            return super().save(path, content, **kwargs)
    
    def read(self, path: str):
        with self._track_operation(OperationType.READ, path):
            return super().read(path)
    
    def delete(self, path: str) -> bool:
        with self._track_operation(OperationType.DELETE, path):
            return super().delete(path)
    
    # ... 其他方法类似


# 使用
class InstrumentedLocalStorage(InstrumentedStorageMixin, LocalStorage):
    """带监控的本地存储"""
    pass

# 集成 Prometheus
def prometheus_callback(backend, operation, success, duration, **extra):
    from prometheus_client import Counter, Histogram
    
    STORAGE_OPS = Counter('storage_operations_total', 'Storage operations', ['backend', 'operation', 'status'])
    STORAGE_DURATION = Histogram('storage_operation_duration_seconds', 'Operation duration', ['backend', 'operation'])
    
    status = 'success' if success else 'error'
    STORAGE_OPS.labels(backend=backend, operation=operation, status=status).inc()
    STORAGE_DURATION.labels(backend=backend, operation=operation).observe(duration / 1000)

collector = MetricsCollector()
collector.on_operation(prometheus_callback)
```

**FastAPI 指标端点**：

```python
@router.get("/metrics")
async def get_metrics():
    """获取存储指标"""
    collector = MetricsCollector()
    return collector.get_all()
```

### 8.5 文件版本管理

**问题**：不支持文件版本控制

**解决方案**：添加版本管理功能

```python
# versioning.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import hashlib
import json

@dataclass
class FileVersion:
    """文件版本"""
    version_id: str           # 版本ID
    path: str                 # 文件路径
    size: int                 # 文件大小
    etag: str                 # 内容哈希
    created_at: datetime      # 创建时间
    created_by: Optional[str] # 创建者
    message: Optional[str]    # 版本说明
    is_current: bool          # 是否为当前版本


class VersionedStorageMixin:
    """版本管理Mixin
    
    为文件存储添加版本控制能力
    """
    
    VERSION_METADATA_KEY = '_versions'
    MAX_VERSIONS = 100  # 每个文件最大版本数
    
    def __init__(self, *args, enable_versioning: bool = True, max_versions: int = 100, **kwargs):
        super().__init__(*args, **kwargs)
        self._versioning_enabled = enable_versioning
        self._max_versions = max_versions
    
    def save(
        self,
        path: str,
        content,
        version_message: Optional[str] = None,
        created_by: Optional[str] = None,
        **kwargs
    ) -> str:
        """保存文件（自动创建版本）"""
        if not self._versioning_enabled:
            return super().save(path, content, **kwargs)
        
        # 读取内容计算哈希
        if isinstance(content, bytes):
            data = content
        else:
            pos = content.tell()
            data = content.read()
            content.seek(pos)
        
        etag = hashlib.sha256(data).hexdigest()[:16]
        
        # 检查是否有变化
        try:
            current = self.get_current_version(path)
            if current and current.etag == etag:
                return path  # 内容未变化，不创建新版本
        except FileNotFoundError:
            pass
        
        # 生成版本ID
        version_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{etag[:8]}"
        
        # 保存版本文件
        version_path = self._version_path(path, version_id)
        super().save(version_path, data, **kwargs)
        
        # 保存当前文件
        result = super().save(path, data, **kwargs)
        
        # 更新版本元数据
        version = FileVersion(
            version_id=version_id,
            path=path,
            size=len(data),
            etag=etag,
            created_at=datetime.now(),
            created_by=created_by,
            message=version_message,
            is_current=True,
        )
        self._add_version(path, version)
        
        return result
    
    def list_versions(self, path: str) -> List[FileVersion]:
        """列出文件的所有版本"""
        metadata_path = self._metadata_path(path)
        try:
            data = super().read_bytes(metadata_path)
            versions_data = json.loads(data)
            return [self._dict_to_version(v) for v in versions_data]
        except FileNotFoundError:
            return []
    
    def get_version(self, path: str, version_id: str) -> bytes:
        """获取指定版本的内容"""
        version_path = self._version_path(path, version_id)
        return super().read_bytes(version_path)
    
    def get_current_version(self, path: str) -> Optional[FileVersion]:
        """获取当前版本信息"""
        versions = self.list_versions(path)
        for v in versions:
            if v.is_current:
                return v
        return None
    
    def restore_version(self, path: str, version_id: str, message: Optional[str] = None) -> str:
        """恢复到指定版本"""
        # 获取版本内容
        content = self.get_version(path, version_id)
        
        # 保存为新版本（带消息）
        return self.save(
            path,
            content,
            version_message=message or f"Restored from {version_id}",
        )
    
    def delete_version(self, path: str, version_id: str) -> bool:
        """删除指定版本"""
        versions = self.list_versions(path)
        version = next((v for v in versions if v.version_id == version_id), None)
        
        if not version:
            return False
        
        if version.is_current:
            raise ValueError("不能删除当前版本")
        
        # 删除版本文件
        version_path = self._version_path(path, version_id)
        super().delete(version_path)
        
        # 更新元数据
        versions = [v for v in versions if v.version_id != version_id]
        self._save_versions_metadata(path, versions)
        
        return True
    
    def _version_path(self, path: str, version_id: str) -> str:
        """版本文件路径"""
        return f"_versions/{path}/{version_id}"
    
    def _metadata_path(self, path: str) -> str:
        """版本元数据路径"""
        return f"_versions/{path}/_metadata.json"
    
    def _add_version(self, path: str, version: FileVersion):
        """添加版本记录"""
        versions = self.list_versions(path)
        
        # 将之前的版本标记为非当前
        for v in versions:
            v.is_current = False
        
        # 添加新版本
        versions.insert(0, version)
        
        # 限制版本数量
        if len(versions) > self._max_versions:
            # 删除最老的版本文件
            for old in versions[self._max_versions:]:
                try:
                    old_path = self._version_path(path, old.version_id)
                    super().delete(old_path)
                except Exception:
                    pass
            versions = versions[:self._max_versions]
        
        self._save_versions_metadata(path, versions)
    
    def _save_versions_metadata(self, path: str, versions: List[FileVersion]):
        """保存版本元数据"""
        metadata_path = self._metadata_path(path)
        data = json.dumps([self._version_to_dict(v) for v in versions], default=str)
        super().save(metadata_path, data.encode())
    
    def _version_to_dict(self, version: FileVersion) -> dict:
        return {
            'version_id': version.version_id,
            'path': version.path,
            'size': version.size,
            'etag': version.etag,
            'created_at': version.created_at.isoformat(),
            'created_by': version.created_by,
            'message': version.message,
            'is_current': version.is_current,
        }
    
    def _dict_to_version(self, data: dict) -> FileVersion:
        return FileVersion(
            version_id=data['version_id'],
            path=data['path'],
            size=data['size'],
            etag=data['etag'],
            created_at=datetime.fromisoformat(data['created_at']),
            created_by=data.get('created_by'),
            message=data.get('message'),
            is_current=data.get('is_current', False),
        )


# 使用
class VersionedLocalStorage(VersionedStorageMixin, LocalStorage):
    """带版本管理的本地存储"""
    pass

storage = VersionedLocalStorage('/data/uploads', max_versions=50)

# 保存文件（自动创建版本）
storage.save('docs/readme.md', content, version_message="Initial version")
storage.save('docs/readme.md', updated_content, version_message="Updated intro")

# 列出版本
versions = storage.list_versions('docs/readme.md')

# 恢复版本
storage.restore_version('docs/readme.md', versions[1].version_id)
```

### 8.6 配置验证增强

**问题**：配置错误可能在运行时才发现

**解决方案**：添加 Pydantic 配置模型和启动时验证

```python
# config.py

from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, Dict, Any, Literal
import os


class BaseStorageConfig(BaseModel):
    """存储配置基类"""
    type: str
    
    class Config:
        extra = 'forbid'  # 禁止额外字段


class MemoryStorageConfig(BaseStorageConfig):
    """内存存储配置"""
    type: Literal['memory'] = 'memory'
    max_size: int = Field(default=100*1024*1024, gt=0, description="最大存储大小（字节）")
    max_files: int = Field(default=10000, gt=0, description="最大文件数")
    
    @validator('max_size')
    def validate_max_size(cls, v):
        if v > 10 * 1024 * 1024 * 1024:  # 10GB
            raise ValueError("内存存储最大不超过 10GB")
        return v


class LocalStorageConfig(BaseStorageConfig):
    """本地存储配置"""
    type: Literal['local'] = 'local'
    base_path: str = Field(..., description="存储根目录")
    base_url: Optional[str] = Field(None, description="访问URL前缀")
    create_dirs: bool = Field(default=True, description="是否自动创建目录")
    
    @validator('base_path')
    def validate_base_path(cls, v):
        # 支持环境变量
        v = os.path.expandvars(v)
        v = os.path.expanduser(v)
        
        # 检查路径是否为绝对路径
        if not os.path.isabs(v):
            raise ValueError(f"base_path 必须是绝对路径: {v}")
        
        return v
    
    @root_validator
    def validate_path_writable(cls, values):
        path = values.get('base_path')
        create_dirs = values.get('create_dirs', True)
        
        if path and os.path.exists(path):
            if not os.access(path, os.W_OK):
                raise ValueError(f"目录不可写: {path}")
        elif not create_dirs:
            raise ValueError(f"目录不存在且 create_dirs=False: {path}")
        
        return values


class OSSStorageConfig(BaseStorageConfig):
    """阿里云 OSS 配置"""
    type: Literal['oss'] = 'oss'
    access_key_id: str = Field(..., min_length=1)
    access_key_secret: str = Field(..., min_length=1)
    endpoint: str = Field(..., regex=r'^[\w.-]+\.aliyuncs\.com$')
    bucket_name: str = Field(..., min_length=1, max_length=63)
    prefix: str = Field(default="", description="存储前缀")
    internal_endpoint: Optional[str] = None
    
    @validator('access_key_id', 'access_key_secret', pre=True)
    def resolve_env_vars(cls, v):
        """支持从环境变量读取"""
        if isinstance(v, str) and v.startswith('${') and v.endswith('}'):
            env_var = v[2:-1]
            value = os.environ.get(env_var)
            if not value:
                raise ValueError(f"环境变量未设置: {env_var}")
            return value
        return v


class S3StorageConfig(BaseStorageConfig):
    """AWS S3 / MinIO 配置"""
    type: Literal['s3'] = 's3'
    access_key_id: str = Field(...)
    secret_access_key: str = Field(...)
    bucket_name: str = Field(...)
    region: str = Field(default='us-east-1')
    endpoint_url: Optional[str] = Field(None, description="自定义端点（MinIO）")
    prefix: str = Field(default="")
    
    @validator('access_key_id', 'secret_access_key', pre=True)
    def resolve_env_vars(cls, v):
        if isinstance(v, str) and v.startswith('${') and v.endswith('}'):
            env_var = v[2:-1]
            value = os.environ.get(env_var)
            if not value:
                raise ValueError(f"环境变量未设置: {env_var}")
            return value
        return v


class SecureURLConfig(BaseModel):
    """安全URL配置"""
    secret_key: str = Field(..., min_length=32, description="密钥（至少32字符）")
    base_url: str = Field(default="/api/files")
    token_store: Literal['memory', 'redis'] = Field(default='memory')
    redis_url: Optional[str] = Field(None, description="Redis连接URL（token_store=redis时必填）")
    
    @validator('secret_key', pre=True)
    def resolve_secret_key(cls, v):
        if isinstance(v, str) and v.startswith('${') and v.endswith('}'):
            env_var = v[2:-1]
            value = os.environ.get(env_var)
            if not value:
                raise ValueError(f"环境变量未设置: {env_var}")
            return value
        return v
    
    @root_validator
    def validate_redis_url(cls, values):
        if values.get('token_store') == 'redis' and not values.get('redis_url'):
            raise ValueError("使用 Redis Token存储时必须配置 redis_url")
        return values


class StorageConfig(BaseModel):
    """完整存储配置"""
    backends: Dict[str, Any] = Field(default_factory=dict)
    default: Optional[str] = Field(None, description="默认后端名称")
    secure_url: Optional[SecureURLConfig] = None
    
    @validator('backends', pre=True)
    def validate_backends(cls, v):
        """验证各后端配置"""
        validated = {}
        config_classes = {
            'memory': MemoryStorageConfig,
            'local': LocalStorageConfig,
            'oss': OSSStorageConfig,
            's3': S3StorageConfig,
        }
        
        for name, config in v.items():
            backend_type = config.get('type')
            if backend_type not in config_classes:
                raise ValueError(f"未知的存储后端类型: {backend_type}")
            
            config_class = config_classes[backend_type]
            validated[name] = config_class(**config)
        
        return validated
    
    @root_validator
    def validate_default(cls, values):
        backends = values.get('backends', {})
        default = values.get('default')
        
        if default and default not in backends:
            raise ValueError(f"默认后端 '{default}' 未在 backends 中定义")
        
        if not default and backends:
            values['default'] = next(iter(backends))
        
        return values


# 使用示例
config_dict = {
    'backends': {
        'local': {
            'type': 'local',
            'base_path': '/data/uploads',
        },
        'oss': {
            'type': 'oss',
            'access_key_id': '${OSS_ACCESS_KEY_ID}',  # 从环境变量读取
            'access_key_secret': '${OSS_ACCESS_KEY_SECRET}',
            'endpoint': 'oss-cn-hangzhou.aliyuncs.com',
            'bucket_name': 'my-bucket',
        },
    },
    'default': 'oss',
    'secure_url': {
        'secret_key': '${STORAGE_SECRET_KEY}',
        'token_store': 'redis',
        'redis_url': 'redis://localhost:6379/0',
    },
}

# 验证配置（在应用启动时）
try:
    config = StorageConfig(**config_dict)
    print("配置验证通过")
except Exception as e:
    print(f"配置错误: {e}")
    exit(1)
```

### 8.7 依赖管理优化

**问题**：可选后端需要 try/except 导入

**解决方案**：使用 extras_require 和延迟导入

```toml
# pyproject.toml

[project]
name = "yweb-storage"
version = "0.1.0"
dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
# 单独安装
local = []  # 无额外依赖
oss = ["oss2>=2.18"]
s3 = ["boto3>=1.26"]
async = ["aiofiles>=23.0"]
redis = ["redis>=4.5"]
validation = ["python-magic>=0.4", "pillow>=10.0"]

# 组合安装
all = ["oss2>=2.18", "boto3>=1.26", "aiofiles>=23.0", "redis>=4.5", "python-magic>=0.4", "pillow>=10.0"]
cloud = ["oss2>=2.18", "boto3>=1.26"]
full = ["yweb-storage[all]"]
```

```python
# _imports.py - 统一的延迟导入管理

from typing import TYPE_CHECKING, Any
import importlib
import warnings

# 后端依赖映射
BACKEND_DEPENDENCIES = {
    'OSSStorage': ('oss2', 'pip install yweb-storage[oss]'),
    'S3Storage': ('boto3', 'pip install yweb-storage[s3]'),
    'AsyncLocalStorage': ('aiofiles', 'pip install yweb-storage[async]'),
    'RedisTokenStore': ('redis', 'pip install yweb-storage[redis]'),
}


class LazyImport:
    """延迟导入包装器"""
    
    def __init__(self, module_path: str, class_name: str, dependency: str, install_hint: str):
        self._module_path = module_path
        self._class_name = class_name
        self._dependency = dependency
        self._install_hint = install_hint
        self._class = None
    
    def __call__(self, *args, **kwargs):
        if self._class is None:
            self._class = self._import()
        return self._class(*args, **kwargs)
    
    def _import(self):
        try:
            importlib.import_module(self._dependency)
        except ImportError:
            raise ImportError(
                f"使用 {self._class_name} 需要安装 {self._dependency}。\n"
                f"请运行: {self._install_hint}"
            )
        
        module = importlib.import_module(self._module_path)
        return getattr(module, self._class_name)
    
    def __getattr__(self, name: str) -> Any:
        if self._class is None:
            self._class = self._import()
        return getattr(self._class, name)


def check_dependency(name: str) -> bool:
    """检查依赖是否可用"""
    dep, _ = BACKEND_DEPENDENCIES.get(name, (None, None))
    if not dep:
        return True
    try:
        importlib.import_module(dep)
        return True
    except ImportError:
        return False


def get_available_backends() -> dict:
    """获取所有可用的后端"""
    available = {
        'memory': True,
        'local': True,
    }
    
    for name, (dep, _) in BACKEND_DEPENDENCIES.items():
        try:
            importlib.import_module(dep)
            backend_name = name.replace('Storage', '').lower()
            available[backend_name] = True
        except ImportError:
            pass
    
    return available


# __init__.py 中使用

# 始终可用的后端
from .backends.memory import MemoryStorage
from .backends.local import LocalStorage

# 延迟导入的可选后端
OSSStorage = LazyImport(
    '.backends.oss', 'OSSStorage',
    'oss2', 'pip install yweb-storage[oss]'
)

S3Storage = LazyImport(
    '.backends.s3', 'S3Storage',
    'boto3', 'pip install yweb-storage[s3]'
)

AsyncLocalStorage = LazyImport(
    '.backends.local_async', 'AsyncLocalStorage',
    'aiofiles', 'pip install yweb-storage[async]'
)

RedisTokenStore = LazyImport(
    '.secure_url', 'RedisTokenStore',
    'redis', 'pip install yweb-storage[redis]'
)

__all__ = [
    'MemoryStorage',
    'LocalStorage',
    'OSSStorage',
    'S3Storage',
    'AsyncLocalStorage',
    'RedisTokenStore',
    'check_dependency',
    'get_available_backends',
]
```

**使用体验**：

```python
# 用户代码
from yweb.storage import OSSStorage, check_dependency

# 检查依赖
if check_dependency('OSSStorage'):
    storage = OSSStorage(...)  # 正常使用
else:
    print("OSS 后端不可用，请安装: pip install yweb-storage[oss]")

# 或直接使用，缺少依赖时会抛出清晰的错误
storage = OSSStorage(...)  # ImportError: 使用 OSSStorage 需要安装 oss2。请运行: pip install yweb-storage[oss]
```

---

## 9. 更新后的实现计划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| **Phase 1** | 核心框架 | P0 |
| | - 抽象基类（同步+异步） | |
| | - Pydantic 配置模型 | |
| | - 内存存储实现 | |
| | - 本地存储实现 | |
| | - 存储管理器 | |
| | - 基础单元测试 | |
| **Phase 2** | 安全访问 | P0 |
| | - SecureURLGenerator | |
| | - Token存储（内存+Redis） | |
| | - 签名URL | |
| | - FastAPI路由集成 | |
| **Phase 3** | 文件验证 | P1 |
| | - FileValidator | |
| | - 预设配置（image/document/avatar） | |
| | - 魔数检测 | |
| | - 图片尺寸验证 | |
| **Phase 4** | 云存储 | P1 |
| | - 阿里云OSS后端（同步+异步） | |
| | - AWS S3后端 | |
| | - MinIO支持 | |
| **Phase 5** | 分片上传 | P1 |
| | - MultipartUploadMixin | |
| | - FastAPI分片端点 | |
| | - 上传任务管理 | |
| **Phase 6** | 监控增强 | P2 |
| | - 指标收集器 | |
| | - 结构化日志 | |
| | - Prometheus集成 | |
| **Phase 7** | 版本管理 | P2 |
| | - VersionedStorageMixin | |
| | - 版本列表/恢复/删除 | |
| | - 版本数量限制 | |

---

## 10. 依赖汇总

| 功能 | 依赖包 | 安装命令 |
|------|--------|---------|
| 核心 | pydantic | 自动安装 |
| 本地存储 | 无 | — |
| 异步支持 | aiofiles | `pip install yweb-storage[async]` |
| 阿里云OSS | oss2 | `pip install yweb-storage[oss]` |
| AWS S3 | boto3 | `pip install yweb-storage[s3]` |
| Redis Token | redis | `pip install yweb-storage[redis]` |
| 文件验证 | python-magic, pillow | `pip install yweb-storage[validation]` |
| 全部功能 | — | `pip install yweb-storage[all]` |
