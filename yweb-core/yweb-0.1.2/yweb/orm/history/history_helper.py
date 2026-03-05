"""
版本历史记录模块

提供 SQLAlchemy 模型的自动版本历史记录功能。
使用 sqlalchemy-history 库实现。

功能特点：
- 自动记录模型的所有变更历史
- 支持查询任意版本的数据
- 无实际变更时不会创建历史记录（配合 base_model 的 event_before_flush）
- 可选择性地为特定模型启用版本历史
- 支持动态主键策略（@declared_attr）与历史记录的兼容

使用示例:
    from yweb.orm import BaseModel, init_versioning, get_history
    from sqlalchemy.orm import Mapped, mapped_column
    from sqlalchemy import String
    
    # 在应用启动时初始化版本化功能
    init_versioning()
    
    # 推荐：使用 BaseModel + enable_history=True
    class User(BaseModel):
        enable_history = True
        __tablename__ = 'user'
        username: Mapped[str] = mapped_column(String(50))
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Type, TypeVar

from sqlalchemy import inspect
from sqlalchemy.orm import Session

# 延迟导入，避免在未安装 sqlalchemy-history 时报错
if TYPE_CHECKING:
    from sqlalchemy_history import version_class

T = TypeVar("T")

# 全局状态：版本化是否已初始化
_versioning_initialized = False


def init_versioning(
    user_cls: Optional[Type] = None,
    transaction_cls: Optional[Type] = None,
    options: Optional[Dict[str, Any]] = None,
    unit_of_work_cls: Optional[Type] = None,
    plugins: Optional[List[Any]] = None,
    builder: Optional[Any] = None,
    manager: Optional[Any] = None
):
    """初始化版本化功能

    此函数应在应用启动时调用，且必须在定义任何 enable_history=True 的模型之前调用。
    
    ⚠️ 重要：如需使用自定义主键策略（如 short_uuid），必须在调用此函数之前
    先调用 configure_primary_key()，因为 Transaction 表的主键类型在此时确定。

    Args:
        user_cls: 可选的用户模型类，用于记录变更操作者
                  如果提供，历史记录会包含操作用户信息
                  - 默认值为 None，sqlalchemy-history 会自动查找名为 "User" 的类
                  - 设置为类名字符串（如 "MyUser"）可指定自定义用户类
                  - 显式设置为 None 可禁用用户追踪
        transaction_cls: 可选的自定义 Transaction 类，用于自定义事务表
                         如果提供，可以自定义事务表的表名和字段
        options: 可选的配置字典，支持以下选项:
                 - table_name: 历史表名模板，默认 '%s_version'，%s 会被替换为原表名
                 - transaction_column_name: 事务ID列名，默认 'transaction_id'
                 - end_transaction_column_name: 结束事务ID列名，默认 'end_transaction_id'
                 - operation_type_column_name: 操作类型列名，默认 'operation_type'
        unit_of_work_cls: 可选的工作单元类，用于处理版本化生命周期操作
                          如果为 None，使用默认的 UnitOfWork 类
        plugins: 可选的插件列表，用于观察版本化事件（如 flush、commit 前后）
                 如需启用用户追踪，请传入 CurrentUserPlugin:
                 init_versioning(plugins=[CurrentUserPlugin()])
        builder: 可选的构建器对象，用于处理版本化模型和架构的构建
                 如果为 None，使用默认构建器
        manager: 可选的 VersioningManager 实例，如果提供，将直接使用此 manager
                 如果提供此参数，其他参数（除 options 外）将被忽略
                 这提供了最大的灵活性，允许完全自定义 VersioningManager

    使用示例:
        # 在 main.py 或 app/__init__.py 中
        from yweb.orm import init_versioning, configure_primary_key

        # ✅ 正确顺序：先配置主键策略，再初始化版本化
        configure_primary_key(strategy="short_uuid", short_uuid_length=10)
        init_versioning()

        # ❌ 错误顺序：这会导致 Transaction 表使用默认的整数主键
        # init_versioning()
        # configure_primary_key(strategy="short_uuid")  # 太晚了！

        # 带用户追踪的初始化（推荐：配合 CurrentUserMiddleware 使用）
        from yweb.orm import CurrentUserPlugin
        init_versioning(
            user_cls=User,
            plugins=[CurrentUserPlugin()]
        )

        # 自定义历史表名模板
        init_versioning(options={'table_name': '%s_history'})

        # 自定义 Transaction 表（需要自己定义 Transaction 类）
        from yweb.orm.sqlalchemy_history.transaction import TransactionBase
        from sqlalchemy import Column, BigInteger, Sequence, String

        class MyTransaction(Base, TransactionBase):
            __tablename__ = "my_audit_log"  # 自定义表名

            id = Column(
                BigInteger,
                Sequence("my_audit_log_id_seq", start=1),
                primary_key=True,
                autoincrement=True,
            )
            remote_addr = Column(String(50))

        init_versioning(transaction_cls=MyTransaction)

        # 使用所有参数的高级配置
        init_versioning(
            user_cls=User,
            transaction_cls=MyTransaction,
            options={'table_name': '%s_history'},
            plugins=[CurrentUserPlugin(), MyCustomPlugin()],
            unit_of_work_cls=MyUnitOfWork
        )

        # 或者直接传入自定义 manager（最大灵活性）
        from sqlalchemy_history.manager import VersioningManager
        custom_manager = VersioningManager(
            transaction_cls=MyTransaction,
            user_cls=User,
            plugins=[CurrentUserPlugin()],
            options={'table_name': '%s_history'}
        )
        init_versioning(manager=custom_manager)

    注意事项:
        - **必须在应用入口统一调用**，不要在每个模型文件中分别调用
        - 重复调用会被自动忽略，确保只调用一次
        - 支持两种初始化顺序：
          1. 先初始化后定义模型（推荐用于应用）
          2. 先定义模型后初始化（用于脚本）
        - 首次创建数据库表时，需要先调用 configure_mappers()
        - 如果需要启动审计，则需要传入 plugins=[CurrentUserPlugin()]
        - 自定义 transaction_cls 时，需要继承 TransactionBase 并定义必要的字段
        - Transaction 表的主键类型会自动读取 PrimaryKeyConfig 配置
        - 如果提供了 manager 参数，将直接使用该 manager，其他参数（除 options 外）将被忽略
    """
    global _versioning_initialized

    if _versioning_initialized:
        return

    try:
        from sqlalchemy_history import make_versioned
        from sqlalchemy_history.manager import VersioningManager
        from sqlalchemy_history.transaction import TransactionBase
        from sqlalchemy import Column, Integer, BigInteger, String
        from ..primary_key_config import PrimaryKeyConfig, IdType
        from ..id_model import Base
        import sqlalchemy_history

        # 如果提供了自定义 manager，直接使用
        if manager is not None:
            sqlalchemy_history.versioning_manager = manager
            make_versioned(manager=manager)
        else:
            # 如果 user_cls 是类对象，转换为字符串（延迟解析，避免注册表查找失败）
            if user_cls is not None and not isinstance(user_cls, str):
                user_cls = user_cls.__name__
            
            # 构建 VersioningManager 的参数字典（排除 user_cls，稍后单独处理）
            manager_kwargs = {
                k: v for k, v in {
                    'transaction_cls': transaction_cls,
                    'options': options,
                    'unit_of_work_cls': unit_of_work_cls,
                    'plugins': plugins,
                    'builder': builder,
                }.items() if v is not None
            }

            # 如果有自定义参数（除了 user_cls），创建 manager 并替换全局对象
            if manager_kwargs:
                # 先不传 user_cls，避免立即查找注册表
                manager = VersioningManager(**manager_kwargs)
                sqlalchemy_history.versioning_manager = manager
                # 启动监听器
                make_versioned(manager=manager)
                # 延迟设置 user_cls（在 configure_mappers 时才会真正查找）
                if user_cls is not None:
                    manager.user_cls = user_cls
            else:
                # 没有特殊参数，使用默认配置
                make_versioned(user_cls=user_cls, options=options)

        _versioning_initialized = True
    except ImportError:
        raise ImportError(
            "sqlalchemy_history 库加载失败"
        )


def is_versioning_initialized() -> bool:
    """检查版本化功能是否已初始化"""
    return _versioning_initialized




def get_version_class(model_class: Type[T]) -> Type:
    """获取模型对应的历史记录类
    
    Args:
        model_class: 原始模型类
    
    Returns:
        对应的历史记录模型类
    
    Raises:
        Exception: 如果模型未启用版本控制
    
    使用示例:
        from yweb.orm import get_version_class
        
        UserHistory = get_version_class(User)
        
        # 直接查询历史表
        all_history = session.query(UserHistory).filter_by(id=1).all()
    """
    try:
        from sqlalchemy_history import version_class as vc
        return vc(model_class)
    except ImportError:
        raise ImportError("sqlalchemy_history 库未找到")
    except Exception as e:
        raise Exception(f"模型 {model_class.__name__} 未启用版本控制: {e}")


def get_history(
    model_class: Type[T],
    instance_id: int,
    version: Optional[int] = None,
    limit: int = 100,
    session: Optional[Session] = None,
    field_names: Optional[List[str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """获取模型实例的历史记录
    
    Args:
        model_class: 模型类
        instance_id: 实例 ID
        version: 可选，指定版本号。None 表示获取所有版本
        limit: 返回的最大记录数，默认 100
        session: 可选的数据库会话。如果不提供，会尝试从 model_class 获取
        field_names: 可选，只返回指定字段。None 表示返回所有字段
    
    Returns:
        历史记录列表（字典格式），按版本号降序排列
        如果没有历史记录，返回 None
    
    使用示例:
        from yweb.orm import get_history
        
        # 获取所有历史记录
        history = get_history(User, user_id=1)
        for record in history:
            print(f"版本 {record['ver']}: {record['name']}")
        
        # 获取特定版本
        history = get_history(User, user_id=1, version=5)
        
        # 只获取特定字段
        history = get_history(User, user_id=1, field_names=['name', 'email', 'ver'])
        
        # 限制返回数量
        history = get_history(User, user_id=1, limit=10)
    """
    try:
        history_model = get_version_class(model_class)
    except Exception as e:
        raise Exception(f"模型 {model_class.__name__} 未启用版本控制: {e}")
    
    # 获取版本号列 - sqlalchemy-history 使用 transaction_id 作为版本标识
    if hasattr(history_model, 'transaction_id'):
        order_col = history_model.transaction_id
    elif hasattr(history_model, 'ver'):
        order_col = history_model.ver
    else:
        order_col = history_model.version
    
    # 获取 session
    if session is None:
        # 尝试从 model_class 获取 session
        if hasattr(model_class, 'query') and hasattr(model_class.query, 'session'):
            session = model_class.query.session
        else:
            insp = inspect(model_class, raiseerr=False)
            if insp and hasattr(insp, 'session'):
                session = insp.session
    
    if session is None:
        raise ValueError("无法获取数据库 session，请显式传入 session 参数")
    
    # 构建查询
    query = session.query(history_model).filter(history_model.id == instance_id)
    query = query.order_by(order_col.desc())
    
    # 过滤特定版本
    if version is not None and version > 0:
        query = query.filter(order_col == version)
    
    # 限制数量
    if limit is not None and limit > 0:
        query = query.limit(limit)
    
    # 执行查询
    if field_names:
        # 只查询指定字段
        selected_entities = []
        for name in field_names:
            col = getattr(history_model, name, None)
            if col is not None:
                selected_entities.append(col)
        
        if selected_entities:
            results = query.with_entities(*selected_entities).all()
            return [row._asdict() for row in results] if results else None
    
    # 查询所有字段
    results = query.all()
    if not results:
        return None
    
    # 转换为字典列表
    return [
        {
            c.key: getattr(obj, c.key)
            for c in inspect(obj).mapper.column_attrs
        }
        for obj in results
    ]


def get_history_count(
    model_class: Type[T],
    instance_id: int,
    session: Optional[Session] = None
) -> int:
    """获取模型实例的历史记录数量
    
    Args:
        model_class: 模型类
        instance_id: 实例 ID
        session: 可选的数据库会话
    
    Returns:
        历史记录数量
    
    Raises:
        Exception: 如果模型未启用版本控制
        ValueError: 如果无法获取数据库 session
    """
    try:
        history_model = get_version_class(model_class)
    except Exception as e:
        raise Exception(f"模型 {model_class.__name__} 未启用版本控制: {e}")
    
    # 获取 session
    if session is None:
        if hasattr(model_class, 'query') and hasattr(model_class.query, 'session'):
            session = model_class.query.session
    
    if session is None:
        raise ValueError("无法获取数据库 session，请传入 session 参数")
    
    from sqlalchemy import func
    return session.query(func.count(history_model.id)).filter(
        history_model.id == instance_id
    ).scalar() or 0


def get_history_diff(
    model_class: Type[T],
    instance_id: int,
    from_version: int,
    to_version: int,
    session: Optional[Session] = None,
    exclude_fields: Optional[set] = None
) -> Optional[Dict[str, Dict[str, Any]]]:
    """比较两个版本之间的差异
    
    Args:
        model_class: 模型类
        instance_id: 实例 ID
        from_version: 起始版本号
        to_version: 目标版本号
        session: 可选的数据库会话
        exclude_fields: 要排除的字段集合
    
    Returns:
        差异字典，格式: {
            "field_name": {"from": old_value, "to": new_value},
            ...
        }
        如果版本不存在，返回 None
    
    使用示例:
        diff = get_history_diff(User, user_id=1, from_version=1, to_version=3)
        for field, change in diff.items():
            print(f"{field}: {change['from']} -> {change['to']}")
    """
    exclude_fields = exclude_fields or {'ver', 'version', 'transaction_id', 'end_transaction_id', 'operation_type'}
    
    # 获取两个版本的数据
    from_data = get_history(model_class, instance_id, version=from_version, session=session)
    to_data = get_history(model_class, instance_id, version=to_version, session=session)
    
    if not from_data or not to_data:
        return None
    
    from_record = from_data[0]
    to_record = to_data[0]
    
    # 计算差异
    diff = {}
    all_keys = set(from_record.keys()) | set(to_record.keys())
    
    for key in all_keys:
        if key in exclude_fields:
            continue
        
        from_value = from_record.get(key)
        to_value = to_record.get(key)
        
        if from_value != to_value:
            diff[key] = {
                "from": from_value,
                "to": to_value
            }
    
    return diff if diff else None


def get_field_text_diff(
    model_class: Type[T],
    instance_id: int,
    field_name: str,
    from_version: int,
    to_version: int,
    session: Optional[Session] = None,
    output_format: Literal["unified", "inline", "html", "opcodes"] = "unified",
    context_lines: int = 3
) -> Optional[Dict[str, Any]]:
    """获取单个字段的文本细节差异
    
    使用 Python difflib 库对比两个版本之间某个字段的文本内容变化，
    支持多种输出格式，适合文章内容、配置文本等长文本的精确对比。
    
    Args:
        model_class: 模型类
        instance_id: 实例 ID
        field_name: 要对比的字段名
        from_version: 起始版本号
        to_version: 目标版本号
        session: 可选的数据库会话
        output_format: 输出格式
            - "unified": 统一格式（类似 git diff），适合查看行级别变更
            - "inline": 行内标记格式，返回结构化列表，便于前端渲染
            - "html": HTML 格式，可直接在浏览器中渲染对比视图
            - "opcodes": 操作码格式，返回详细的操作指令，便于程序处理
        context_lines: 上下文行数，仅 unified 和 html 格式有效，默认 3
    
    Returns:
        差异字典，格式: {
            "field": 字段名,
            "from_version": 起始版本号,
            "to_version": 目标版本号,
            "from_value": 原始值,
            "to_value": 新值,
            "diff": 差异结果（格式取决于 output_format）,
            "stats": {"added": n, "removed": n, "changed": n}  # 行级统计
        }
        如果版本不存在，返回 None
    
    使用示例:
        # 获取文章内容的 unified diff（类似 git diff）
        detail = get_field_text_diff(
            Article, 
            instance_id=1, 
            field_name="content",
            from_version=1, 
            to_version=3,
            output_format="unified"
        )
        print(detail["diff"])
        
        # 获取 HTML 格式，用于前端展示
        detail = get_field_text_diff(
            Article, 1, "content", 1, 3,
            output_format="html"
        )
        # detail["diff"] 是可直接渲染的 HTML 表格
        
        # 获取 opcodes 格式，用于程序处理
        detail = get_field_text_diff(
            Article, 1, "content", 1, 3,
            output_format="opcodes"
        )
        for op in detail["diff"]:
            if op["operation"] == "replace":
                print(f"替换: '{op['from_text']}' -> '{op['to_text']}'")
    """
    from difflib import HtmlDiff, SequenceMatcher, unified_diff
    
    # 获取两个版本的数据
    from_data = get_history(
        model_class, instance_id, version=from_version,
        session=session, field_names=[field_name]
    )
    to_data = get_history(
        model_class, instance_id, version=to_version,
        session=session, field_names=[field_name]
    )
    
    if not from_data or not to_data:
        return None
    
    from_value = from_data[0].get(field_name, "") or ""
    to_value = to_data[0].get(field_name, "") or ""
    
    # 转换为字符串（处理非字符串类型）
    from_text = str(from_value)
    to_text = str(to_value)
    
    # 按行分割（保留换行符以便 unified_diff 正确处理）
    from_lines = from_text.splitlines(keepends=True)
    to_lines = to_text.splitlines(keepends=True)
    
    # 如果最后一行没有换行符，添加空字符串以保持一致性
    if from_lines and not from_lines[-1].endswith('\n'):
        from_lines[-1] += '\n'
    if to_lines and not to_lines[-1].endswith('\n'):
        to_lines[-1] += '\n'
    
    result: Dict[str, Any] = {
        "field": field_name,
        "from_version": from_version,
        "to_version": to_version,
        "from_value": from_value,
        "to_value": to_value,
    }
    
    if output_format == "unified":
        # 统一格式（类似 git diff）
        diff_lines = list(unified_diff(
            from_lines, to_lines,
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            n=context_lines
        ))
        result["diff"] = "".join(diff_lines)
        
    elif output_format == "html":
        # HTML 格式
        differ = HtmlDiff()
        result["diff"] = differ.make_table(
            from_lines, to_lines,
            fromdesc=f"版本 {from_version}",
            todesc=f"版本 {to_version}",
            context=True,
            numlines=context_lines
        )
        
    elif output_format == "opcodes":
        # 操作码格式（便于程序处理）- 基于字符级别
        matcher = SequenceMatcher(None, from_text, to_text)
        opcodes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            opcodes.append({
                "operation": tag,  # 'equal', 'replace', 'insert', 'delete'
                "from_start": i1,
                "from_end": i2,
                "to_start": j1,
                "to_end": j2,
                "from_text": from_text[i1:i2] if tag != 'insert' else None,
                "to_text": to_text[j1:j2] if tag != 'delete' else None,
            })
        result["diff"] = opcodes
        
    else:  # inline
        # 行内标记格式
        matcher = SequenceMatcher(None, from_lines, to_lines)
        inline_diff: List[Dict[str, Any]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                inline_diff.extend([
                    {"type": "equal", "text": line.rstrip('\n')} 
                    for line in from_lines[i1:i2]
                ])
            elif tag == 'delete':
                inline_diff.extend([
                    {"type": "delete", "text": line.rstrip('\n')} 
                    for line in from_lines[i1:i2]
                ])
            elif tag == 'insert':
                inline_diff.extend([
                    {"type": "insert", "text": line.rstrip('\n')} 
                    for line in to_lines[j1:j2]
                ])
            elif tag == 'replace':
                inline_diff.extend([
                    {"type": "delete", "text": line.rstrip('\n')} 
                    for line in from_lines[i1:i2]
                ])
                inline_diff.extend([
                    {"type": "insert", "text": line.rstrip('\n')} 
                    for line in to_lines[j1:j2]
                ])
        result["diff"] = inline_diff
    
    # 行级统计信息
    line_matcher = SequenceMatcher(None, from_lines, to_lines)
    stats = {"added": 0, "removed": 0, "changed": 0}
    for tag, i1, i2, j1, j2 in line_matcher.get_opcodes():
        if tag == 'insert':
            stats["added"] += j2 - j1
        elif tag == 'delete':
            stats["removed"] += i2 - i1
        elif tag == 'replace':
            stats["changed"] += max(i2 - i1, j2 - j1)
    result["stats"] = stats
    
    return result


def restore_to_version(
    model_class: Type[T],
    instance_id: int,
    version: int,
    session: Optional[Session] = None,
    exclude_fields: Optional[set] = None
) -> Optional[T]:
    """恢复实例到指定版本
    
    此方法会从历史记录中读取指定版本的数据，并更新当前实例。
    
    Args:
        model_class: 模型类
        instance_id: 实例 ID
        version: 要恢复到的版本号
        session: 可选的数据库会话
        exclude_fields: 恢复时要排除的字段
    
    Returns:
        更新后的实例对象
        如果版本不存在或实例不存在，返回 None
    
    使用示例:
        # 恢复用户到版本 5
        user = restore_to_version(User, user_id=1, version=5)
        session.commit()
    
    注意事项:
        - 此操作会创建一条新的历史记录
        - 排除字段默认包含: id, ver, version, created_at, updated_at 等
    """
    exclude_fields = exclude_fields or {
        'id', 'ver', 'version', 'transaction_id', 'end_transaction_id', 
        'operation_type', 'created_at'
    }
    
    # 获取历史版本数据
    history_data = get_history(model_class, instance_id, version=version, session=session)
    if not history_data:
        return None
    
    history_record = history_data[0]
    
    # 获取 session
    if session is None:
        if hasattr(model_class, 'query') and hasattr(model_class.query, 'session'):
            session = model_class.query.session
    
    if session is None:
        raise ValueError("无法获取数据库 session")
    
    # 获取当前实例
    instance = session.query(model_class).filter_by(id=instance_id).first()
    if not instance:
        return None
    
    # 更新实例属性
    for key, value in history_record.items():
        if key not in exclude_fields and hasattr(instance, key):
            setattr(instance, key, value)
    
    return instance


# 导出的公共 API
__all__ = [
    "init_versioning",
    "is_versioning_initialized",
    "get_version_class",
    "get_history",
    "get_history_count",
    "get_history_diff",
    "get_field_text_diff",
    "restore_to_version",
]

