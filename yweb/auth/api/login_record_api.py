"""登录记录查询路由

提供登录记录的搜索查询能力，基于 AbstractLoginRecord 的内置字段。

端点列表：
    GET /list  - 查询登录记录（用户名 + IP + 状态过滤 + 分页）

使用示例::

    from yweb.auth.api import create_login_record_router

    lr_router = create_login_record_router(LoginRecord)
    app.include_router(lr_router, prefix="/api/v1/login-records", tags=["login-records"])
"""

from typing import Type, Optional, TYPE_CHECKING

from fastapi import APIRouter, Query

from yweb.response import Resp, PageResponse
from yweb.orm import DTO

if TYPE_CHECKING:
    from ..models import AbstractLoginRecord


def create_login_record_router(
    login_record_model: Type["AbstractLoginRecord"],
) -> APIRouter:
    """创建登录记录查询路由

    Args:
        login_record_model: 登录记录模型类（AbstractLoginRecord 的子类）

    Returns:
        APIRouter，包含登录记录查询路由
    """
    router = APIRouter()

    # ==================== DTO 定义 ====================

    class LoginRecordItem(DTO):
        """登录记录响应"""
        username: str = ""
        ip_address: str = ""
        user_agent: Optional[str] = None
        created_at: str = ""
        status: str = ""
        failure_reason: Optional[str] = None

    # ==================== 路由定义 ====================

    @router.get("/list", response_model=PageResponse[LoginRecordItem], summary="查询登录记录")
    async def list_login_records(
        username: Optional[str] = Query(None, description="用户名，支持模糊查询"),
        ip_address: Optional[str] = Query(None, description="登录IP地址"),
        status: Optional[str] = Query(None, description="登录状态 (success, failed, pending)"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    ):
        """查询登录记录

        根据用户名、IP地址、状态等条件查询登录记录
        """
        query = login_record_model.query.with_entities(
            login_record_model.username,
            login_record_model.ip_address,
            login_record_model.user_agent,
            login_record_model.created_at,
            login_record_model.status,
            login_record_model.failure_reason,
        ).order_by(login_record_model.created_at.desc())

        if username:
            query = query.filter(login_record_model.username.ilike(f"%{username}%"))
        if ip_address:
            query = query.filter(login_record_model.ip_address.ilike(f"%{ip_address}%"))
        if status:
            query = query.filter(login_record_model.status == status.lower())

        page_result = query.paginate(page=page, page_size=page_size)
        return Resp.OK(LoginRecordItem.from_page(page_result))

    return router
