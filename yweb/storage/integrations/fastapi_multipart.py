# -*- coding: utf-8 -*-
"""
FastAPI 分片上传路由

提供大文件分片上传的 REST API 端点：
- 初始化上传
- 上传分片
- 完成上传
- 取消上传
- 查询分片列表

使用示例:
    from fastapi import FastAPI
    from yweb.storage.integrations.fastapi_multipart import create_multipart_router
    
    app = FastAPI()
    
    # 创建分片上传路由
    router = create_multipart_router(
        get_current_user=get_current_user,  # 可选：认证依赖
        storage_name=None,  # 可选：指定存储后端名称
    )
    
    app.include_router(router, prefix="/api/storage")
"""

from typing import Optional, Callable, List, Any

__all__ = ['create_multipart_router']


def create_multipart_router(
    get_current_user: Optional[Callable] = None,
    storage_name: Optional[str] = None,
    prefix: str = "/multipart",
    tags: Optional[List[str]] = None,
) -> Any:
    """创建分片上传路由
    
    Args:
        get_current_user: 获取当前用户的依赖函数（可选）
        storage_name: 存储后端名称，None 使用默认后端
        prefix: 路由前缀
        tags: OpenAPI 标签
        
    Returns:
        APIRouter: FastAPI 路由实例
        
    Example:
        router = create_multipart_router(
            get_current_user=get_current_user,
        )
        app.include_router(router, prefix="/api/storage")
        
        # 客户端使用流程：
        # 1. POST /api/storage/multipart/init - 初始化上传
        # 2. PUT /api/storage/multipart/{upload_id}/parts/{part_number} - 上传分片
        # 3. POST /api/storage/multipart/{upload_id}/complete - 完成上传
    """
    from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Body, Query
    from pydantic import BaseModel, Field
    
    from ..manager import StorageManager
    from ..multipart import MultipartUploadMixin
    from ..exceptions import (
        UploadNotFound,
        UploadExpired,
        PartNumberInvalid,
        PartVerificationFailed,
        MultipartUploadError,
    )
    
    router = APIRouter(prefix=prefix, tags=tags or ["multipart-upload"])
    
    # ==================== 请求/响应模型 ====================
    
    class InitUploadRequest(BaseModel):
        """初始化上传请求"""
        path: str = Field(..., description="目标文件路径")
        content_type: Optional[str] = Field(None, description="MIME类型")
        metadata: Optional[dict] = Field(None, description="自定义元数据")
        expires_in: Optional[int] = Field(None, description="上传任务过期时间（秒）")
    
    class InitUploadResponse(BaseModel):
        """初始化上传响应"""
        upload_id: str = Field(..., description="上传任务ID")
        path: str = Field(..., description="目标文件路径")
        expires_in: int = Field(..., description="过期时间（秒）")
    
    class UploadPartResponse(BaseModel):
        """上传分片响应"""
        part_number: int = Field(..., description="分片序号")
        etag: str = Field(..., description="分片ETag")
        size: int = Field(..., description="分片大小")
    
    class PartInfo(BaseModel):
        """分片信息（用于完成上传时验证）"""
        part_number: int = Field(..., description="分片序号")
        etag: str = Field(..., description="分片ETag")
    
    class CompleteUploadRequest(BaseModel):
        """完成上传请求"""
        parts: Optional[List[PartInfo]] = Field(None, description="分片列表（用于验证）")
    
    class CompleteUploadResponse(BaseModel):
        """完成上传响应"""
        path: str = Field(..., description="最终文件路径")
        size: int = Field(..., description="文件总大小")
    
    class UploadInfoResponse(BaseModel):
        """上传任务信息响应"""
        upload_id: str
        path: str
        content_type: Optional[str]
        created_at: str
        expires_at: str
        total_size: int
        part_count: int
        parts: List[dict]
    
    # ==================== 辅助函数 ====================
    
    def _get_storage() -> MultipartUploadMixin:
        """获取支持分片上传的存储后端"""
        storage = StorageManager.get(storage_name)
        
        if not isinstance(storage, MultipartUploadMixin):
            raise HTTPException(
                status_code=501,
                detail="当前存储后端不支持分片上传，请使用 MultipartUploadMixin"
            )
        
        return storage
    
    def _handle_multipart_error(e: Exception) -> None:
        """处理分片上传异常"""
        if isinstance(e, UploadNotFound):
            raise HTTPException(status_code=404, detail=str(e))
        elif isinstance(e, UploadExpired):
            raise HTTPException(status_code=410, detail=str(e))
        elif isinstance(e, PartNumberInvalid):
            raise HTTPException(status_code=400, detail=str(e))
        elif isinstance(e, PartVerificationFailed):
            raise HTTPException(status_code=400, detail=str(e))
        elif isinstance(e, MultipartUploadError):
            raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=500, detail=f"分片上传错误: {e}")
    
    # ==================== 端点 ====================
    
    @router.post(
        "/init",
        response_model=InitUploadResponse,
        summary="初始化分片上传",
        description="创建一个新的分片上传任务，返回上传ID用于后续操作",
    )
    async def init_multipart_upload(
        request: InitUploadRequest,
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """初始化分片上传
        
        创建一个新的分片上传任务。返回的 upload_id 需要在后续操作中使用。
        
        流程：
        1. 调用此接口获取 upload_id
        2. 使用 upload_id 上传各个分片
        3. 所有分片上传完成后调用完成接口
        """
        storage = _get_storage()
        
        try:
            upload_id = storage.init_multipart_upload(
                path=request.path,
                content_type=request.content_type,
                metadata=request.metadata,
                expires_in=request.expires_in,
            )
            
            # 获取上传信息以返回过期时间
            upload_info = storage.get_upload_info(upload_id)
            expires_in = int((upload_info.expires_at - upload_info.created_at).total_seconds())
            
            return InitUploadResponse(
                upload_id=upload_id,
                path=request.path,
                expires_in=expires_in,
            )
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.put(
        "/{upload_id}/parts/{part_number}",
        response_model=UploadPartResponse,
        summary="上传分片",
        description="上传一个文件分片",
    )
    async def upload_part(
        upload_id: str,
        part_number: int,
        file: UploadFile = File(..., description="分片文件内容"),
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """上传分片
        
        上传指定序号的分片。分片序号从 1 开始，最大 10000。
        同一序号的分片可以重复上传（会覆盖之前的）。
        
        建议分片大小：5MB - 100MB
        """
        storage = _get_storage()
        
        try:
            content = await file.read()
            
            part = storage.upload_part(
                upload_id=upload_id,
                part_number=part_number,
                content=content,
            )
            
            return UploadPartResponse(
                part_number=part.part_number,
                etag=part.etag,
                size=part.size,
            )
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.post(
        "/{upload_id}/complete",
        response_model=CompleteUploadResponse,
        summary="完成分片上传",
        description="合并所有分片，完成上传",
    )
    async def complete_multipart_upload(
        upload_id: str,
        request: CompleteUploadRequest = Body(default=None),
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """完成分片上传
        
        将所有已上传的分片合并为最终文件。
        
        可选地提供 parts 列表用于验证分片的完整性。
        如果不提供，则使用服务端记录的分片信息。
        """
        storage = _get_storage()
        
        try:
            # 获取当前上传信息以计算最终大小
            upload_info = storage.get_upload_info(upload_id)
            total_size = upload_info.total_size
            
            # 准备验证参数
            parts = None
            if request and request.parts:
                parts = [
                    {'part_number': p.part_number, 'etag': p.etag}
                    for p in request.parts
                ]
            
            path = storage.complete_multipart_upload(
                upload_id=upload_id,
                parts=parts,
            )
            
            return CompleteUploadResponse(
                path=path,
                size=total_size,
            )
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.delete(
        "/{upload_id}",
        summary="取消分片上传",
        description="取消上传任务，删除所有已上传的分片",
    )
    async def abort_multipart_upload(
        upload_id: str,
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """取消分片上传
        
        取消上传任务并删除所有已上传的分片。
        """
        storage = _get_storage()
        
        try:
            success = storage.abort_multipart_upload(upload_id)
            
            if success:
                return {"status": "aborted", "upload_id": upload_id}
            else:
                raise HTTPException(status_code=500, detail="取消上传失败")
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.get(
        "/{upload_id}",
        response_model=UploadInfoResponse,
        summary="获取上传任务信息",
        description="查询上传任务的详细信息",
    )
    async def get_upload_info(
        upload_id: str,
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """获取上传任务信息
        
        查询上传任务的详细信息，包括已上传的分片列表。
        """
        storage = _get_storage()
        
        try:
            upload = storage.get_upload_info(upload_id)
            
            return UploadInfoResponse(
                upload_id=upload.upload_id,
                path=upload.path,
                content_type=upload.content_type,
                created_at=upload.created_at.isoformat(),
                expires_at=upload.expires_at.isoformat(),
                total_size=upload.total_size,
                part_count=upload.part_count,
                parts=[p.to_dict() for p in upload.parts],
            )
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.get(
        "/{upload_id}/parts",
        summary="列出已上传的分片",
        description="获取已上传分片的列表",
    )
    async def list_parts(
        upload_id: str,
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """列出已上传的分片
        
        返回指定上传任务的所有已上传分片信息。
        """
        storage = _get_storage()
        
        try:
            parts = storage.list_parts(upload_id)
            
            return {
                "upload_id": upload_id,
                "parts": [
                    {
                        "part_number": p.part_number,
                        "etag": p.etag,
                        "size": p.size,
                        "uploaded_at": p.uploaded_at.isoformat(),
                    }
                    for p in parts
                ]
            }
        except Exception as e:
            _handle_multipart_error(e)
    
    @router.get(
        "",
        summary="列出进行中的上传任务",
        description="获取所有进行中的上传任务列表",
    )
    async def list_uploads(
        path_prefix: str = Query("", description="路径前缀过滤"),
        current_user: Any = Depends(get_current_user) if get_current_user else None,
    ):
        """列出进行中的上传任务
        
        获取所有未过期的上传任务列表。
        可以通过 path_prefix 参数过滤特定路径下的任务。
        """
        storage = _get_storage()
        
        try:
            uploads = storage.list_uploads(path_prefix)
            
            return {
                "uploads": [
                    {
                        "upload_id": u.upload_id,
                        "path": u.path,
                        "created_at": u.created_at.isoformat(),
                        "expires_at": u.expires_at.isoformat(),
                        "total_size": u.total_size,
                        "part_count": u.part_count,
                    }
                    for u in uploads
                ]
            }
        except Exception as e:
            _handle_multipart_error(e)
    
    return router
