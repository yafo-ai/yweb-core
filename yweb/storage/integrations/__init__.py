# -*- coding: utf-8 -*-
"""
框架集成模块

提供与各种 Web 框架的集成：
- FastAPI: 文件访问路由、上传端点

使用示例:
    from yweb.storage.integrations.fastapi import create_storage_router
    
    router = create_storage_router(secure_url_generator=secure_url)
    app.include_router(router)
"""

__all__ = ['create_storage_router', 'create_multipart_router']


def __getattr__(name: str):
    """延迟导入"""
    if name == 'create_storage_router':
        from .fastapi import create_storage_router
        return create_storage_router
    if name == 'create_multipart_router':
        from .fastapi_multipart import create_multipart_router
        return create_multipart_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
