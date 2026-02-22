"""各种主键类型测试演示

本脚本演示了 yweb.orm 支持的所有主键类型，每种类型都分别测试：
1. 不带历史表的模型
2. 带历史表的模型

================================================================================
                          主键类型概述
================================================================================

支持的主键类型（IdType）：
┌─────────────────────────────────────────────────────────────────────────────┐
│ AUTO_INCREMENT  - 整数自增（数据库自增，默认）                              │
│ SNOWFLAKE       - 雪花ID（64位整数，适合分布式系统）                        │
│ UUID            - 完整UUID（36位字符串，全局唯一）                          │
│ SHORT_UUID      - 短UUID（8-32位可配置，兼顾可读性和唯一性）                │
│ CUSTOM          - 自定义生成器（完全自定义主键生成逻辑）                    │
└─────────────────────────────────────────────────────────────────────────────┘

使用方式：
1. 全局配置：configure_primary_key(strategy=IdType.XXX)
2. 模型级别覆盖：在模型类中设置 __pk_strategy__ = IdType.XXX

历史表配置：
- 在模型类中设置 enable_history = True 即可启用版本历史

运行方式：
    python demo_primary_key_types.py
"""

import os
import sys
from datetime import datetime
from sqlalchemy import String, Text
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column


# ==================== 1. 初始化版本化功能 ====================
# 必须在定义任何带历史记录的模型之前调用

from yweb.orm import init_versioning, IdType, configure_primary_key, PrimaryKeyConfig

try:
    init_versioning()
    print("[OK] 版本化功能初始化成功")
except Exception as e:
    print(f"[INFO] 版本化已初始化或出错: {e}")


# ==================== 2. 导入依赖 ====================

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    get_history,
    get_history_count,
    is_versioning_initialized,
)


# ==================== 辅助函数 ====================

def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(message: str):
    """打印成功消息"""
    print(f"[OK] {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"[ERROR] {message}")


def print_info(message: str):
    """打印信息"""
    print(f"[INFO] {message}")


def print_test_result(test_name: str, passed: bool, details: str = ""):
    """打印测试结果"""
    status = "✓ 通过" if passed else "✗ 失败"
    print(f"  {status} - {test_name}")
    if details:
        print(f"         {details}")


# ==================== 3. 定义各种主键类型的模型 ====================

# --------------- 1. 自增主键 (AUTO_INCREMENT) ---------------

class AutoIncrementModel(BaseModel):
    """自增主键模型 - 不带历史表"""
    __tablename__ = "demo_auto_increment"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.AUTO_INCREMENT
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


class AutoIncrementHistoryModel(BaseModel):
    """自增主键模型 - 带历史表"""
    __tablename__ = "demo_auto_increment_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.AUTO_INCREMENT
    
    enable_history = True
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


# --------------- 2. 雪花ID (SNOWFLAKE) ---------------

class SnowflakeModel(BaseModel):
    """雪花ID模型 - 不带历史表"""
    __tablename__ = "demo_snowflake"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


class SnowflakeHistoryModel(BaseModel):
    """雪花ID模型 - 带历史表"""
    __tablename__ = "demo_snowflake_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    
    enable_history = True
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


# --------------- 3. UUID ---------------

class UUIDModel(BaseModel):
    """UUID主键模型 - 不带历史表"""
    __tablename__ = "demo_uuid"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.UUID
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


class UUIDHistoryModel(BaseModel):
    """UUID主键模型 - 带历史表"""
    __tablename__ = "demo_uuid_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.UUID
    
    enable_history = True
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


# --------------- 4. 短UUID (SHORT_UUID) ---------------

class ShortUUIDModel(BaseModel):
    """短UUID主键模型 - 不带历史表"""
    __tablename__ = "demo_short_uuid"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


class ShortUUIDHistoryModel(BaseModel):
    """短UUID主键模型 - 带历史表"""
    __tablename__ = "demo_short_uuid_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    enable_history = True
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


# --------------- 5. 自定义生成器 (CUSTOM) ---------------

# 定义一个自定义主键生成器
_custom_counter = 0

def custom_id_generator() -> str:
    """自定义主键生成器 - 生成带前缀的ID"""
    global _custom_counter
    _custom_counter += 1
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"CUSTOM_{timestamp}_{_custom_counter:06d}"


class CustomModel(BaseModel):
    """自定义主键模型 - 不带历史表"""
    __tablename__ = "demo_custom"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.CUSTOM
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


class CustomHistoryModel(BaseModel):
    """自定义主键模型 - 带历史表"""
    __tablename__ = "demo_custom_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.CUSTOM
    
    enable_history = True
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)


# ==================== 4. 测试场景 ====================

def test_model(
    model_class,
    model_name: str,
    pk_type: str,
    has_history: bool,
    session
) -> bool:
    """测试单个模型
    
    Args:
        model_class: 模型类
        model_name: 模型名称（用于显示）
        pk_type: 主键类型描述
        has_history: 是否带历史表
        session: 数据库会话
    
    Returns:
        测试是否通过
    """
    test_passed = True
    history_suffix = "（带历史表）" if has_history else "（不带历史表）"
    
    try:
        # 1. 创建记录
        obj = model_class(
            name=f"测试{pk_type}",
            code=f"TEST_{pk_type.upper()}",
            title=f"测试标题 - {pk_type}",
            content=f"测试内容 - {datetime.now()}"
        )
        obj.add(True)
        obj_id = obj.id
        
        # 验证主键已生成
        if obj_id is None:
            print_test_result(f"创建记录 {history_suffix}", False, "主键为空")
            return False
        
        print_test_result(f"创建记录 {history_suffix}", True, f"ID={obj_id} (类型: {type(obj_id).__name__})")
        
        # 2. 更新记录
        obj.title = f"更新后的标题 - {pk_type}"
        obj.content = f"更新后的内容 - {datetime.now()}"
        obj.save(True)
        
        # 验证更新
        updated_obj = model_class.get(obj_id)
        if updated_obj and "更新后" in updated_obj.title:
            print_test_result(f"更新记录 {history_suffix}", True)
        else:
            print_test_result(f"更新记录 {history_suffix}", False, "更新后查询失败或内容不对")
            test_passed = False
        
        # 3. 第二次更新（触发更多历史记录）
        obj.title = f"第二次更新 - {pk_type}"
        obj.save(True)
        
        # 4. 验证历史记录（如果启用）
        if has_history:
            try:
                history_count = get_history_count(model_class, obj_id, session=session)
                if history_count >= 1:
                    print_test_result(f"历史记录 {history_suffix}", True, f"共 {history_count} 条历史记录")
                else:
                    print_test_result(f"历史记录 {history_suffix}", False, "没有找到历史记录")
                    test_passed = False
                
                # 获取历史详情
                history_list = get_history(model_class, obj_id, session=session)
                if history_list:
                    print_info(f"    最近一条历史: transaction_id={history_list[0].get('transaction_id')}")
            except Exception as e:
                print_test_result(f"历史记录 {history_suffix}", False, f"查询历史失败: {e}")
                test_passed = False
        
        # 5. 软删除
        obj.delete(True)
        
        # 验证软删除
        deleted_obj = model_class.get(obj_id)
        if deleted_obj is None or deleted_obj.deleted_at is not None:
            print_test_result(f"软删除 {history_suffix}", True)
        else:
            print_test_result(f"软删除 {history_suffix}", False, "软删除失败")
            test_passed = False
        
        return test_passed
        
    except Exception as e:
        print_test_result(f"{model_name} {history_suffix}", False, f"异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_auto_increment(session):
    """测试自增主键类型"""
    print_section("1. 自增主键 (AUTO_INCREMENT)")
    print_info("特点：数据库自动递增整数，简单高效")
    print_info("适用场景：单机系统、不需要分布式ID的场景\n")
    
    results = []
    
    # 不带历史表
    results.append(test_model(
        AutoIncrementModel, "AutoIncrementModel",
        "auto_increment", False, session
    ))
    
    print()  # 空行分隔
    
    # 带历史表
    results.append(test_model(
        AutoIncrementHistoryModel, "AutoIncrementHistoryModel",
        "auto_increment", True, session
    ))
    
    return all(results)


def test_snowflake(session):
    """测试雪花ID主键类型"""
    print_section("2. 雪花ID (SNOWFLAKE)")
    print_info("特点：64位整数，时间戳+工作节点ID+序列号")
    print_info("适用场景：分布式系统、高并发场景、需要ID有序的场景\n")
    
    results = []
    
    # 不带历史表
    results.append(test_model(
        SnowflakeModel, "SnowflakeModel",
        "snowflake", False, session
    ))
    
    print()
    
    # 带历史表
    results.append(test_model(
        SnowflakeHistoryModel, "SnowflakeHistoryModel",
        "snowflake", True, session
    ))
    
    return all(results)


def test_uuid(session):
    """测试UUID主键类型"""
    print_section("3. UUID")
    print_info("特点：36位字符串（含4个连字符），全局唯一")
    print_info("适用场景：需要全局唯一性、分布式系统、跨系统数据同步\n")
    
    results = []
    
    # 不带历史表
    results.append(test_model(
        UUIDModel, "UUIDModel",
        "uuid", False, session
    ))
    
    print()
    
    # 带历史表
    results.append(test_model(
        UUIDHistoryModel, "UUIDHistoryModel",
        "uuid", True, session
    ))
    
    return all(results)


def test_short_uuid(session):
    """测试短UUID主键类型"""
    print_section("4. 短UUID (SHORT_UUID)")
    print_info(f"特点：可配置长度（8-32位），当前配置长度: {PrimaryKeyConfig.get_short_uuid_length()}")
    print_info("适用场景：需要可读性更好的ID、URL友好、手动输入场景\n")
    
    results = []
    
    # 不带历史表
    results.append(test_model(
        ShortUUIDModel, "ShortUUIDModel",
        "short_uuid", False, session
    ))
    
    print()
    
    # 带历史表
    results.append(test_model(
        ShortUUIDHistoryModel, "ShortUUIDHistoryModel",
        "short_uuid", True, session
    ))
    
    return all(results)


def test_custom(session):
    """测试自定义主键类型"""
    print_section("5. 自定义生成器 (CUSTOM)")
    print_info("特点：完全自定义主键生成逻辑")
    print_info("当前生成器格式：CUSTOM_年月日时分秒_序号\n")
    
    # 配置自定义生成器
    original_strategy = PrimaryKeyConfig.get_strategy()
    original_generator = PrimaryKeyConfig.get_custom_generator()
    
    try:
        # 设置自定义生成器
        configure_primary_key(
            strategy=IdType.CUSTOM,
            custom_generator=custom_id_generator
        )
        
        results = []
        
        # 不带历史表
        results.append(test_model(
            CustomModel, "CustomModel",
            "custom", False, session
        ))
        
        print()
        
        # 带历史表
        results.append(test_model(
            CustomHistoryModel, "CustomHistoryModel",
            "custom", True, session
        ))
        
        return all(results)
        
    finally:
        # 恢复原配置
        if original_generator:
            configure_primary_key(
                strategy=original_strategy,
                custom_generator=original_generator
            )
        else:
            PrimaryKeyConfig.reset()


def test_batch_creation(session):
    """测试批量创建"""
    print_section("6. 批量创建测试")
    print_info("测试各种主键类型的批量创建性能和唯一性\n")
    
    all_passed = True
    batch_size = 10
    
    models_to_test = [
        (AutoIncrementModel, "AUTO_INCREMENT"),
        (SnowflakeModel, "SNOWFLAKE"),
        (UUIDModel, "UUID"),
        (ShortUUIDModel, "SHORT_UUID"),
    ]
    
    for model_class, pk_type in models_to_test:
        try:
            # 批量创建
            objects = []
            for i in range(batch_size):
                obj = model_class(
                    name=f"批量测试{i}",
                    code=f"BATCH_{pk_type}_{i}",
                    title=f"批量创建标题 {i}",
                    content=f"批量创建内容 {i}"
                )
                objects.append(obj)
            
            model_class.add_all(objects, commit=True)
            
            # 验证唯一性
            ids = [obj.id for obj in objects]
            unique_ids = set(ids)
            
            if len(ids) == len(unique_ids):
                print_test_result(
                    f"{pk_type} 批量创建 {batch_size} 条",
                    True,
                    f"所有ID唯一，示例: {ids[0]}"
                )
            else:
                print_test_result(
                    f"{pk_type} 批量创建 {batch_size} 条",
                    False,
                    f"ID冲突! 预期{len(ids)}个唯一ID，实际{len(unique_ids)}个"
                )
                all_passed = False
                
        except Exception as e:
            print_test_result(f"{pk_type} 批量创建", False, f"异常: {e}")
            all_passed = False
    
    return all_passed


def test_mixed_pk_types(session):
    """测试混合主键类型场景"""
    print_section("7. 混合主键类型场景")
    print_info("演示在同一个应用中使用不同主键类型的模型\n")
    
    try:
        # 同时创建不同类型主键的记录
        auto_obj = AutoIncrementModel(
            name="混合测试-自增",
            code="MIX_AUTO",
            title="自增主键记录"
        )
        auto_obj.add(True)
        
        snow_obj = SnowflakeModel(
            name="混合测试-雪花",
            code="MIX_SNOW",
            title="雪花主键记录"
        )
        snow_obj.add(True)
        
        uuid_obj = UUIDModel(
            name="混合测试-UUID",
            code="MIX_UUID",
            title="UUID主键记录"
        )
        uuid_obj.add(True)
        
        short_obj = ShortUUIDModel(
            name="混合测试-短UUID",
            code="MIX_SHORT",
            title="短UUID主键记录"
        )
        short_obj.add(True)
        
        # 显示各个记录的ID
        print_info("各模型ID类型和值：")
        print(f"  AutoIncrement: {type(auto_obj.id).__name__:10} -> {auto_obj.id}")
        print(f"  Snowflake:     {type(snow_obj.id).__name__:10} -> {snow_obj.id}")
        print(f"  UUID:          {type(uuid_obj.id).__name__:10} -> {uuid_obj.id}")
        print(f"  ShortUUID:     {type(short_obj.id).__name__:10} -> {short_obj.id}")
        
        print()
        print_success("混合主键类型场景测试通过！")
        return True
        
    except Exception as e:
        print_error(f"混合主键类型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("  各种主键类型测试演示")
    print("="*70)
    
    # 检查版本化状态
    if is_versioning_initialized():
        print_success("版本化功能已启用")
    else:
        print_error("版本化功能未初始化！")
        return
    
    # 初始化数据库
    print_info("初始化数据库...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_primary_key_types.db")
    
    # 删除旧数据库（确保测试干净）
    if os.path.exists(db_path):
        os.remove(db_path)
        print_info("已删除旧数据库文件")
    
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    # 设置 query 属性
    CoreModel.query = session_scope.query_property()
    
    # 配置 mappers（必须在创建表之前）
    print_info("配置版本映射...")
    try:
        configure_mappers()
        print_success("版本映射配置完成")
    except Exception as e:
        print_info(f"mappers 已配置: {e}")
    
    # 创建数据表
    print_info("创建数据表...")
    BaseModel.metadata.create_all(engine)
    print_success("数据库初始化完成")
    
    # 获取 session
    session = session_scope()
    
    # 运行所有测试
    test_results = {}
    
    try:
        # 1. 自增主键
        test_results["AUTO_INCREMENT"] = test_auto_increment(session)
        
        # 2. 雪花ID
        test_results["SNOWFLAKE"] = test_snowflake(session)
        
        # 3. UUID
        test_results["UUID"] = test_uuid(session)
        
        # 4. 短UUID
        test_results["SHORT_UUID"] = test_short_uuid(session)
        
        # 5. 自定义生成器
        test_results["CUSTOM"] = test_custom(session)
        
        # 6. 批量创建
        test_results["BATCH"] = test_batch_creation(session)
        
        # 7. 混合场景
        test_results["MIXED"] = test_mixed_pk_types(session)
        
        # 打印总结
        print_section("测试总结")
        
        all_passed = True
        for test_name, passed in test_results.items():
            status = "✓ 通过" if passed else "✗ 失败"
            print(f"  {status} - {test_name}")
            if not passed:
                all_passed = False
        
        print()
        if all_passed:
            print_success("所有测试通过！")
        else:
            print_error("部分测试失败，请检查日志")
        
    except Exception as e:
        print_error(f"测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        session_scope.remove()
        print()
        print_info(f"数据库文件保存在: {db_path}")


if __name__ == "__main__":
    main()
