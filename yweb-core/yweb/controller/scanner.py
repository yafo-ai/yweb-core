"""
控制器自动扫描 —— 扫描指定包下所有 ResourceController 子类并挂载路由。

适合约定式项目结构，一行代码完成所有控制器注册::

    from yweb.controller import scan_controllers

    app = FastAPI()
    scan_controllers(app, package="app.api.v1", prefix="/api/v1")
"""

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

from .base import ResourceController


def scan_controllers(app: "FastAPI", package: str, prefix: str = ""):
    """
    扫描包下所有 ResourceController 子类，自动 include_router。

    Args:
        app: FastAPI 应用实例
        package: 要扫描的 Python 包路径（如 "app.api.v1"）
        prefix: 全局路由前缀（如 "/api/v1"）
    """
    pkg = importlib.import_module(package)
    pkg_path = getattr(pkg, "__path__", None)
    if pkg_path is None:
        _scan_module(app, pkg, prefix)
        return

    for _, module_name, _ in pkgutil.walk_packages(
        pkg_path, prefix=f"{package}."
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        _scan_module(app, module, prefix)


def _scan_module(app: "FastAPI", module, prefix: str):
    """扫描单个模块中的 ResourceController 子类。"""
    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if obj is None:
            continue
        if (
            isinstance(obj, type)
            and issubclass(obj, ResourceController)
            and obj is not ResourceController
            and hasattr(obj, "router")
            and "prefix" in obj.__dict__
        ):
            app.include_router(obj.router, prefix=prefix)
