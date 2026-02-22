# 存储模块使用指南

## 安装

```bash
# 核心功能
pip install yweb

# 按需安装可选依赖
pip install yweb[oss]          # 阿里云 OSS
pip install yweb[s3]           # AWS S3 / MinIO
pip install yweb[validation]   # 文件验证增强
pip install yweb[storage-all]  # 全部存储功能
```

## 快速开始

### 1. 基础使用

```python
from yweb.storage import StorageManager
from yweb.storage.backends import LocalStorage

# 注册本地存储
storage = LocalStorage(base_path="./uploads")
StorageManager.register("local", storage, default=True)

# 使用
storage = StorageManager.get()
storage.save("images/photo.jpg", image_bytes)
content = storage.read("images/photo.jpg")
```

### 2. 配置文件方式（推荐）

```python
from yweb.config import StorageSettings
from yweb.storage import StorageManager

# 从环境变量自动加载
settings = StorageSettings()
StorageManager.init_from_settings(settings)

# 或手动配置
settings = StorageSettings(
    default="local",
    local={"base_path": "/data/uploads", "base_url": "/static"},
    oss={"enabled": True, "bucket_name": "my-bucket"},
)
StorageManager.init_from_settings(settings)
```

**环境变量**：
```bash
YWEB_STORAGE_DEFAULT=local
YWEB_STORAGE_LOCAL_BASE_PATH=/data/uploads
YWEB_STORAGE_OSS_ENABLED=true
YWEB_STORAGE_OSS_BUCKET_NAME=my-bucket
```

**YAML 配置**：
```yaml
storage:
  default: local
  local:
    base_path: /data/uploads
    base_url: /static/uploads
  oss:
    enabled: true
    access_key_id: ${OSS_ACCESS_KEY_ID}
    access_key_secret: ${OSS_ACCESS_KEY_SECRET}
    endpoint: oss-cn-hangzhou.aliyuncs.com
    bucket_name: my-bucket
```

## 存储后端

### 本地存储

```python
from yweb.storage.backends import LocalStorage

storage = LocalStorage(
    base_path="./uploads",      # 存储根目录
    base_url="/static/uploads", # URL 前缀（可选）
    create_dirs=True,           # 自动创建目录
)

# 保存文件
path = storage.save("docs/file.pdf", file_bytes)

# 读取文件
content = storage.read("docs/file.pdf")

# 获取文件信息
info = storage.get_info("docs/file.pdf")
# FileInfo(path='docs/file.pdf', size=1024, content_type='application/pdf', ...)

# 列出文件
files = storage.list(prefix="docs/", recursive=True)

# 获取访问 URL
url = storage.get_url("docs/file.pdf")  # /static/uploads/docs/file.pdf

# 复制/移动
storage.copy("docs/file.pdf", "backup/file.pdf")
storage.move("temp/file.pdf", "docs/file.pdf")

# 删除
storage.delete("docs/file.pdf")
```

### 内存存储

适用于缓存、测试场景：

```python
from yweb.storage.backends import MemoryStorage

storage = MemoryStorage(
    max_size=100 * 1024 * 1024,  # 100MB
    max_files=10000,
)
```

### 阿里云 OSS

```python
from yweb.storage.backends import OSSStorage

storage = OSSStorage(
    access_key_id="your-key-id",
    access_key_secret="your-key-secret",
    endpoint="oss-cn-hangzhou.aliyuncs.com",
    bucket_name="my-bucket",
    prefix="uploads/",  # 可选路径前缀
)

# 获取签名 URL（临时访问）
url = storage.get_url("file.pdf", expires=3600)

# 获取上传 URL（客户端直传）
upload_url = storage.get_upload_url("file.pdf", expires=600)
```

### AWS S3 / MinIO

```python
from yweb.storage.backends import S3Storage

# AWS S3
storage = S3Storage(
    access_key_id="your-key-id",
    secret_access_key="your-secret",
    bucket_name="my-bucket",
    region="us-east-1",
)

# MinIO（自建对象存储）
storage = S3Storage(
    access_key_id="minioadmin",
    secret_access_key="minioadmin",
    bucket_name="my-bucket",
    endpoint_url="http://localhost:9000",
)
```

## 高级功能

### 文件验证

```python
from yweb.storage import FileValidator, ValidatedStorageMixin
from yweb.storage.backends import LocalStorage

# 使用预设
validator = FileValidator(preset="image")  # 支持 image/document/avatar/video

# 自定义验证
from yweb.storage import FileValidationConfig

config = FileValidationConfig(
    max_size=10 * 1024 * 1024,        # 10MB
    allowed_extensions=[".jpg", ".png", ".pdf"],
    blocked_extensions=[".exe", ".sh"],
)
validator = FileValidator(config=config)

# 验证文件
result = validator.validate(file_bytes, filename="test.jpg")
if not result.valid:
    print(result.errors)

# 集成到存储后端
class ValidatedLocalStorage(ValidatedStorageMixin, LocalStorage):
    pass

storage = ValidatedLocalStorage(
    base_path="./uploads",
    validator=validator,
)
storage.save("test.jpg", file_bytes)  # 自动验证
```

### 安全 URL（临时访问链接）

```python
from yweb.storage import SecureURLGenerator, MemoryTokenStore

generator = SecureURLGenerator(
    secret_key="your-secret-key",
    base_url="/files",
    token_store=MemoryTokenStore(),
)

# 生成临时访问链接
secure_url = generator.generate(
    backend_name="local",
    path="private/report.pdf",
    expires=3600,           # 1小时有效
    max_downloads=3,        # 最多下载3次
    user_id="user123",      # 限制用户
)
print(secure_url.url)  # /files/abc123?signature=xxx

# 验证访问
token_info = generator.validate(token="abc123", user_id="user123")
if token_info:
    # 允许访问
    pass
```

### FastAPI 集成

#### 基础：文件上传接口

```python
from fastapi import FastAPI, UploadFile, File, HTTPException
from yweb.storage import StorageManager
from yweb.config import StorageSettings

app = FastAPI()

# 初始化存储
settings = StorageSettings(local={"base_path": "./uploads", "base_url": "/static"})
StorageManager.init_from_settings(settings)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """简单文件上传"""
    storage = StorageManager.get()
    
    content = await file.read()
    path = f"files/{file.filename}"
    
    storage.save(path, content)
    
    return {"path": path, "url": storage.get_url(path)}
```

#### 基础：带验证的文件上传

```python
from fastapi import FastAPI, UploadFile, File, HTTPException
from yweb.storage import StorageManager, FileValidator

app = FastAPI()
validator = FileValidator(preset="image")


@app.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """图片上传（带验证）"""
    content = await file.read()
    
    # 验证文件
    result = validator.validate(content, filename=file.filename)
    if not result.valid:
        raise HTTPException(400, detail={"errors": result.errors})
    
    # 保存
    storage = StorageManager.get()
    path = f"images/{file.filename}"
    storage.save(path, content)
    
    return {
        "path": path,
        "size": result.size,
        "mime_type": result.detected_mime,
    }
```

#### 基础：文件下载接口

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from yweb.storage import StorageManager

app = FastAPI()


@app.get("/download/{path:path}")
async def download_file(path: str):
    """文件下载"""
    storage = StorageManager.get()
    
    if not storage.exists(path):
        raise HTTPException(404, detail="文件不存在")
    
    info = storage.get_info(path)
    content = storage.read(path)
    
    return StreamingResponse(
        content,
        media_type=info.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{info.path.split("/")[-1]}"'
        },
    )
```

#### 进阶：安全文件访问（临时链接）

```python
from fastapi import FastAPI, Depends, HTTPException
from yweb.storage import StorageManager, SecureURLGenerator, MemoryTokenStore
from yweb.storage.integrations import create_storage_router

app = FastAPI()

# 安全 URL 生成器
generator = SecureURLGenerator(
    secret_key="your-secret-key-change-in-production",
    base_url="/files",
    token_store=MemoryTokenStore(),
    default_expires=3600,
)

# 注册安全文件访问路由
# 自动提供: GET /files/{token} 端点
app.include_router(
    create_storage_router(
        secret_key="your-secret-key-change-in-production",
        prefix="/files",
    )
)


def get_current_user():
    """模拟获取当前用户"""
    return {"id": "user123", "name": "张三"}


@app.post("/documents/{doc_id}/share")
async def create_share_link(
    doc_id: str,
    expires: int = 3600,
    max_downloads: int = 10,
    user = Depends(get_current_user),
):
    """生成文档分享链接"""
    storage = StorageManager.get()
    path = f"documents/{doc_id}.pdf"
    
    if not storage.exists(path):
        raise HTTPException(404, detail="文档不存在")
    
    # 生成安全链接
    secure_url = generator.generate(
        backend_name="local",
        path=path,
        expires=expires,
        max_downloads=max_downloads,
        user_id=user["id"],  # 限制只有该用户可访问
        metadata={"doc_id": doc_id, "shared_by": user["name"]},
    )
    
    return {
        "share_url": secure_url.url,
        "expires_at": secure_url.expires_at.isoformat(),
        "max_downloads": max_downloads,
    }
```

#### 进阶：多后端文件管理

```python
from fastapi import FastAPI, UploadFile, File, Query
from yweb.storage import StorageManager
from yweb.config import StorageSettings

app = FastAPI()

# 配置多个后端
settings = StorageSettings(
    default="local",
    local={"base_path": "./uploads", "base_url": "/static"},
    memory={"enabled": True},
    oss={"enabled": True, "bucket_name": "my-bucket"},  # 需要配置密钥
)
StorageManager.init_from_settings(settings)


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    backend: str = Query("local", description="存储后端: local/memory/oss"),
):
    """上传到指定后端"""
    storage = StorageManager.get(backend)
    content = await file.read()
    
    path = f"uploads/{file.filename}"
    storage.save(path, content)
    
    return {
        "backend": backend,
        "path": path,
        "url": storage.get_url(path) if hasattr(storage, 'get_url') else None,
    }


@app.get("/files")
async def list_files(
    backend: str = Query("local"),
    prefix: str = Query("", description="路径前缀"),
):
    """列出文件"""
    storage = StorageManager.get(backend)
    files = storage.list(prefix=prefix, recursive=True)
    
    return {
        "backend": backend,
        "files": [
            {"path": f.path, "size": f.size, "modified": f.modified_at.isoformat()}
            for f in files
        ],
    }
```

#### 高级：分片上传 API

```python
from fastapi import FastAPI, UploadFile, File, HTTPException
from yweb.storage import MultipartUploadMixin
from yweb.storage.backends import LocalStorage
from yweb.storage.integrations import create_multipart_router

app = FastAPI()


# 创建支持分片上传的存储
class MultipartLocalStorage(MultipartUploadMixin, LocalStorage):
    pass


storage = MultipartLocalStorage(base_path="./uploads")


# 方式1：使用内置路由（推荐）
app.include_router(
    create_multipart_router(
        prefix="/upload/multipart",
        tags=["分片上传"],
    )
)
# 自动提供以下端点:
# POST   /upload/multipart/init              - 初始化上传
# PUT    /upload/multipart/{id}/parts/{num}  - 上传分片
# POST   /upload/multipart/{id}/complete     - 完成上传
# DELETE /upload/multipart/{id}              - 取消上传
# GET    /upload/multipart/{id}              - 获取上传状态
# GET    /upload/multipart/{id}/parts        - 列出已上传分片


# 方式2：手动实现（更灵活）
@app.post("/upload/init")
async def init_upload(filename: str, total_size: int):
    """初始化分片上传"""
    upload = storage.init_multipart_upload(
        path=f"large-files/{filename}",
        expires=7200,  # 2小时内完成
    )
    
    return {
        "upload_id": upload.upload_id,
        "expires_at": upload.expires_at.isoformat(),
    }


@app.put("/upload/{upload_id}/parts/{part_number}")
async def upload_part(
    upload_id: str,
    part_number: int,
    file: UploadFile = File(...),
):
    """上传分片"""
    content = await file.read()
    
    part = storage.upload_part(
        upload_id=upload_id,
        part_number=part_number,
        content=content,
    )
    
    return {"part_number": part.part_number, "etag": part.etag, "size": part.size}


@app.post("/upload/{upload_id}/complete")
async def complete_upload(upload_id: str):
    """完成上传"""
    path = storage.complete_multipart_upload(upload_id, verify_parts=True)
    return {"path": path, "url": f"/static/{path}"}
```

#### 高级：完整文件管理服务

```python
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from yweb.storage import (
    StorageManager,
    FileValidator,
    SecureURLGenerator,
    MemoryTokenStore,
    MetricsCollector,
    ValidatedStorageMixin,
    VersionedStorageMixin,
    InstrumentedStorageMixin,
)
from yweb.storage.backends import LocalStorage
from yweb.config import StorageSettings

app = FastAPI(title="文件管理服务")


# ==================== 初始化 ====================

class FullFeaturedStorage(
    ValidatedStorageMixin,
    VersionedStorageMixin,
    InstrumentedStorageMixin,
    LocalStorage,
):
    """完整功能存储：验证 + 版本 + 监控"""
    pass


# 文件验证器
image_validator = FileValidator(preset="image")
document_validator = FileValidator(preset="document")

# 存储实例
storage = FullFeaturedStorage(
    base_path="./uploads",
    base_url="/static",
    validator=document_validator,
    enable_versioning=True,
    max_versions=10,
)
StorageManager.register("default", storage, default=True)

# 安全 URL
url_generator = SecureURLGenerator(
    secret_key="change-this-in-production",
    base_url="/secure",
    token_store=MemoryTokenStore(),
)


# ==================== 数据模型 ====================

class FileUploadResponse(BaseModel):
    path: str
    size: int
    content_type: str
    url: str
    version_id: Optional[str] = None


class FileListResponse(BaseModel):
    files: List[dict]
    total: int


class ShareLinkResponse(BaseModel):
    url: str
    expires_at: datetime
    max_downloads: int


# ==================== 接口 ====================

@app.post("/files/upload", response_model=FileUploadResponse, tags=["文件操作"])
async def upload_file(
    file: UploadFile = File(...),
    path: str = Query(None, description="自定义保存路径"),
    message: str = Query(None, description="版本备注"),
):
    """
    上传文件
    
    - 自动验证文件类型和大小
    - 自动创建版本记录
    - 返回访问 URL
    """
    content = await file.read()
    
    # 确定保存路径
    save_path = path or f"uploads/{datetime.now():%Y%m%d}/{file.filename}"
    
    # 保存（自动验证 + 版本记录）
    try:
        storage.save(save_path, content, message=message)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    
    info = storage.get_info(save_path)
    version = storage.get_current_version(save_path)
    
    return FileUploadResponse(
        path=save_path,
        size=info.size,
        content_type=info.content_type,
        url=storage.get_url(save_path),
        version_id=version.version_id if version else None,
    )


@app.get("/files", response_model=FileListResponse, tags=["文件操作"])
async def list_files(
    prefix: str = Query("", description="路径前缀"),
    limit: int = Query(100, le=1000),
):
    """列出文件"""
    files = storage.list(prefix=prefix, limit=limit)
    
    return FileListResponse(
        files=[
            {
                "path": f.path,
                "size": f.size,
                "content_type": f.content_type,
                "modified_at": f.modified_at.isoformat(),
            }
            for f in files
        ],
        total=len(files),
    )


@app.get("/files/download/{path:path}", tags=["文件操作"])
async def download_file(path: str):
    """下载文件"""
    if not storage.exists(path):
        raise HTTPException(404, detail="文件不存在")
    
    info = storage.get_info(path)
    content = storage.read(path)
    filename = path.split("/")[-1]
    
    return StreamingResponse(
        content,
        media_type=info.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/files/{path:path}", tags=["文件操作"])
async def delete_file(path: str, keep_versions: bool = Query(False)):
    """删除文件"""
    if not storage.exists(path):
        raise HTTPException(404, detail="文件不存在")
    
    storage.delete(path)
    
    if not keep_versions:
        storage.delete_all_versions(path)
    
    return {"message": "删除成功", "path": path}


@app.get("/files/{path:path}/versions", tags=["版本管理"])
async def list_versions(path: str):
    """查看文件版本历史"""
    versions = storage.list_versions(path)
    
    return {
        "path": path,
        "versions": [
            {
                "version_id": v.version_id,
                "size": v.size,
                "created_at": v.created_at.isoformat(),
                "message": v.message,
                "is_current": v.is_current,
            }
            for v in versions
        ],
    }


@app.post("/files/{path:path}/restore/{version_id}", tags=["版本管理"])
async def restore_version(path: str, version_id: str):
    """恢复到指定版本"""
    new_version = storage.restore_version(path, version_id)
    
    return {
        "message": "恢复成功",
        "new_version_id": new_version.version_id,
    }


@app.post("/files/{path:path}/share", response_model=ShareLinkResponse, tags=["分享"])
async def create_share_link(
    path: str,
    expires: int = Query(3600, description="有效期（秒）"),
    max_downloads: int = Query(10, description="最大下载次数"),
):
    """生成分享链接"""
    if not storage.exists(path):
        raise HTTPException(404, detail="文件不存在")
    
    secure_url = url_generator.generate(
        backend_name="default",
        path=path,
        expires=expires,
        max_downloads=max_downloads,
    )
    
    return ShareLinkResponse(
        url=secure_url.url,
        expires_at=secure_url.expires_at,
        max_downloads=max_downloads,
    )


@app.get("/metrics", tags=["监控"])
async def get_metrics():
    """获取存储统计"""
    metrics = MetricsCollector.get_or_create("default")
    
    return {
        "uptime_seconds": metrics.uptime_seconds,
        "total_operations": metrics.total_operations,
        "total_errors": metrics.total_errors,
        "operations": {
            op_type.value: op_metrics.to_dict()
            for op_type, op_metrics in metrics.operations.items()
        },
    }


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**前端调用示例**：

```javascript
// 上传文件
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/files/upload?message=初始版本', {
  method: 'POST',
  body: formData,
});
const result = await response.json();
console.log(result.url);

// 获取分享链接
const shareResponse = await fetch('/files/documents/report.pdf/share?expires=7200', {
  method: 'POST',
});
const shareResult = await shareResponse.json();
console.log(shareResult.url);  // /secure/abc123?signature=xxx

// 查看版本历史
const versions = await fetch('/files/documents/report.pdf/versions').then(r => r.json());
console.log(versions);
```

### 分片上传

```python
from yweb.storage import MultipartUploadMixin
from yweb.storage.backends import LocalStorage

class MultipartLocalStorage(MultipartUploadMixin, LocalStorage):
    pass

storage = MultipartLocalStorage(base_path="./uploads")

# 初始化上传
upload = storage.init_multipart_upload("large-file.zip")

# 上传分片
storage.upload_part(upload.upload_id, part_number=1, content=chunk1)
storage.upload_part(upload.upload_id, part_number=2, content=chunk2)

# 完成上传
path = storage.complete_multipart_upload(upload.upload_id)
```

### 文件版本管理

```python
from yweb.storage import VersionedStorageMixin
from yweb.storage.backends import LocalStorage

class VersionedLocalStorage(VersionedStorageMixin, LocalStorage):
    pass

storage = VersionedLocalStorage(
    base_path="./uploads",
    enable_versioning=True,
    max_versions=10,
)

# 保存（自动创建版本）
storage.save("doc.txt", b"v1", message="初始版本")
storage.save("doc.txt", b"v2", message="修改内容")

# 查看版本历史
versions = storage.list_versions("doc.txt")

# 恢复历史版本
storage.restore_version("doc.txt", version_id="xxx")
```

### 操作监控

```python
from yweb.storage import InstrumentedStorageMixin, MetricsCollector
from yweb.storage.backends import LocalStorage

class MonitoredLocalStorage(InstrumentedStorageMixin, LocalStorage):
    pass

storage = MonitoredLocalStorage(base_path="./uploads")

# 使用存储...
storage.save("file.txt", b"content")
storage.read("file.txt")

# 获取统计
metrics = MetricsCollector.get_or_create("local")
print(metrics.to_dict())
# {
#   'total_operations': 2,
#   'operations': {
#     'SAVE': {'count': 1, 'total_bytes': 7, ...},
#     'READ': {'count': 1, ...}
#   }
# }
```

## 功能组合

Mixin 可以自由组合：

```python
from yweb.storage import (
    ValidatedStorageMixin,
    VersionedStorageMixin,
    InstrumentedStorageMixin,
)
from yweb.storage.backends import LocalStorage

class FullFeaturedStorage(
    ValidatedStorageMixin,
    VersionedStorageMixin,
    InstrumentedStorageMixin,
    LocalStorage,
):
    """验证 + 版本 + 监控"""
    pass

storage = FullFeaturedStorage(
    base_path="./uploads",
    validator=FileValidator(preset="document"),
    enable_versioning=True,
)
```

## 常见场景

### 用户头像上传

```python
from yweb.storage import StorageManager, FileValidator

validator = FileValidator(preset="avatar")
storage = StorageManager.get()

def upload_avatar(user_id: str, file: bytes, filename: str):
    # 验证
    result = validator.validate(file, filename)
    if not result.valid:
        raise ValueError(result.errors)
    
    # 保存
    path = f"avatars/{user_id}.jpg"
    storage.save(path, file, overwrite=True)
    return storage.get_url(path)
```

### 私有文件下载

```python
from yweb.storage import StorageManager, SecureURLGenerator

generator = SecureURLGenerator(secret_key="xxx", base_url="/download")

def get_download_link(user_id: str, file_path: str):
    secure_url = generator.generate(
        backend_name="local",
        path=file_path,
        expires=300,        # 5分钟
        max_downloads=1,    # 仅一次
        user_id=user_id,
    )
    return secure_url.url
```

### 大文件断点续传

```python
from yweb.storage.integrations import create_multipart_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(create_multipart_router(prefix="/upload"))

# 前端调用：
# POST /upload/init         -> 获取 upload_id
# PUT  /upload/{id}/parts/1 -> 上传分片
# POST /upload/{id}/complete -> 完成上传
```
