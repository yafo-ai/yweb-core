# -*- coding: utf-8 -*-
"""
FastAPI 集成模块

提供文件访问的 FastAPI 路由，支持：
- Token访问（/t/{token}）
- 签名URL访问（/s/{path}?e=...&s=...）

使用示例:
    from fastapi import FastAPI
    from yweb.storage import StorageManager, SecureURLGenerator
    from yweb.storage.integrations.fastapi import create_storage_router
    
    app = FastAPI()
    
    # 初始化
    StorageManager.register('local', LocalStorage('/data'))
    secure_url = SecureURLGenerator(secret_key="your-secret-key")
    
    # 注册路由
    router = create_storage_router(secure_url_generator=secure_url)
    app.include_router(router)
"""

import logging
from typing import Optional, Callable, List, Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


def create_storage_router(
    secure_url_generator: Any,
    get_current_user: Optional[Callable] = None,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    storage_name: Optional[str] = None,
):
    """创建文件访问路由
    
    Args:
        secure_url_generator: SecureURLGenerator 实例
        get_current_user: 获取当前用户的依赖函数（可选）
            - 异步函数，接收 Request，返回用户对象或 None
            - 用户对象需要有 id 属性
        prefix: 路由前缀（默认为空，使用 SecureURLGenerator 的 base_url）
        tags: OpenAPI 标签
        storage_name: 使用的存储后端名称（默认使用默认后端）
        
    Returns:
        APIRouter: FastAPI 路由
        
    Example:
        from yweb.storage.integrations.fastapi import create_storage_router
        
        # 基本用法
        router = create_storage_router(
            secure_url_generator=secure_url,
        )
        app.include_router(router)
        
        # 带用户认证
        async def get_current_user_optional(request: Request):
            # 从 request 获取用户信息
            return request.state.user if hasattr(request.state, 'user') else None
        
        router = create_storage_router(
            secure_url_generator=secure_url,
            get_current_user=get_current_user_optional,
        )
        app.include_router(router)
    """
    # 延迟导入，避免在不使用 FastAPI 时报错
    try:
        from fastapi import APIRouter, HTTPException, Request, Query
        from fastapi.responses import StreamingResponse, Response
    except ImportError:
        raise ImportError(
            "使用 FastAPI 集成需要安装 fastapi: pip install fastapi"
        )
    
    from ..manager import StorageManager
    from ..exceptions import StorageError
    
    # 使用 secure_url_generator 的 base_url 作为前缀
    if not prefix:
        prefix = secure_url_generator.base_url
    
    router = APIRouter(prefix=prefix, tags=tags or ["files"])
    
    async def _get_user_id(request: Request) -> Optional[int]:
        """获取当前用户ID"""
        if get_current_user is None:
            return None
        
        try:
            user = await get_current_user(request)
            if user is None:
                return None
            return getattr(user, 'id', None)
        except Exception as e:
            logger.debug(f"获取用户ID失败: {e}")
            return None
    
    def _get_storage():
        """获取存储后端"""
        return StorageManager.get(storage_name)
    
    def _build_content_disposition(filename: str, force_download: bool = True) -> str:
        """构建 Content-Disposition 头"""
        disposition_type = "attachment" if force_download else "inline"
        
        # 检查文件名是否包含非 ASCII 字符
        try:
            filename.encode('ascii')
            # 纯 ASCII 文件名
            return f'{disposition_type}; filename="{filename}"'
        except UnicodeEncodeError:
            # 包含非 ASCII 字符，使用 RFC 5987 编码
            encoded_filename = quote(filename)
            return f"{disposition_type}; filename*=UTF-8''{encoded_filename}"
    
    @router.get("/t/{token}")
    async def get_file_by_token(
        token: str,
        request: Request,
    ):
        """通过Token访问文件
        
        Token访问支持：
        - 用户限制（仅指定用户可访问）
        - 下载次数限制
        - 过期时间
        - 强制下载（Content-Disposition: attachment）
        """
        user_id = await _get_user_id(request)
        
        # 验证Token
        info = secure_url_generator.validate_token(token, user_id)
        if info is None:
            raise HTTPException(
                status_code=404,
                detail="文件不存在或链接已过期",
            )
        
        # 获取文件
        try:
            storage = _get_storage()
            content = storage.read(info.file_path)
            file_info = storage.get_info(info.file_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="文件不存在",
            )
        except StorageError as e:
            logger.error(f"读取文件失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="文件读取失败",
            )
        
        # 构建响应头
        headers = {}
        
        # Content-Disposition
        if info.download:
            filename = info.filename or file_info.filename
            headers['Content-Disposition'] = _build_content_disposition(filename, True)
        
        # ETag
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        # Content-Length
        headers['Content-Length'] = str(file_info.size)
        
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
        
        签名URL特点：
        - 无需登录
        - 可公开分享
        - 有过期时间
        - 无下载次数限制
        """
        # 验证签名
        file_path = secure_url_generator.validate_signed(encoded_path, e, s)
        if file_path is None:
            raise HTTPException(
                status_code=404,
                detail="链接无效或已过期",
            )
        
        # 获取文件
        try:
            storage = _get_storage()
            content = storage.read(file_path)
            file_info = storage.get_info(file_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="文件不存在",
            )
        except StorageError as e:
            logger.error(f"读取文件失败: {e}")
            raise HTTPException(
                status_code=500,
                detail="文件读取失败",
            )
        
        # 构建响应头
        headers = {}
        
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        headers['Content-Length'] = str(file_info.size)
        
        return StreamingResponse(
            content,
            media_type=file_info.content_type or 'application/octet-stream',
            headers=headers,
        )
    
    @router.head("/t/{token}")
    async def head_file_by_token(
        token: str,
        request: Request,
    ):
        """获取文件元信息（Token方式）
        
        用于预检文件大小、类型等，不消耗下载次数。
        """
        user_id = await _get_user_id(request)
        
        # 验证Token（不增加下载计数）
        info = secure_url_generator.token_store.get(token)
        if info is None:
            raise HTTPException(
                status_code=404,
                detail="文件不存在或链接已过期",
            )
        
        # 检查用户限制
        if info.user_id is not None and info.user_id != user_id:
            raise HTTPException(
                status_code=404,
                detail="文件不存在或链接已过期",
            )
        
        try:
            storage = _get_storage()
            file_info = storage.get_info(info.file_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="文件不存在",
            )
        
        headers = {
            'Content-Length': str(file_info.size),
            'Content-Type': file_info.content_type or 'application/octet-stream',
        }
        
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        return Response(headers=headers)
    
    @router.head("/s/{encoded_path:path}")
    async def head_file_by_signature(
        encoded_path: str,
        e: int = Query(..., description="过期时间戳"),
        s: str = Query(..., description="签名"),
    ):
        """获取文件元信息（签名URL方式）"""
        # 验证签名
        file_path = secure_url_generator.validate_signed(encoded_path, e, s)
        if file_path is None:
            raise HTTPException(
                status_code=404,
                detail="链接无效或已过期",
            )
        
        try:
            storage = _get_storage()
            file_info = storage.get_info(file_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="文件不存在",
            )
        
        headers = {
            'Content-Length': str(file_info.size),
            'Content-Type': file_info.content_type or 'application/octet-stream',
        }
        
        if file_info.etag:
            headers['ETag'] = f'"{file_info.etag}"'
        
        return Response(headers=headers)
    
    return router


__all__ = ['create_storage_router']
