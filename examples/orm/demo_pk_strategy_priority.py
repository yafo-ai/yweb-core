"""主键策略优先级测试演示

本脚本验证主键策略的优先级规则：
    模型级别配置 > 全局配置 > 默认值

================================================================================
                          优先级规则说明
================================================================================

优先级从高到低：
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 模型级别配置：id_type 或者 __pk_strategy__ = IdType.XXX                    │
│    - 在模型类中直接设置，优先级最高                                            │
│    - 如果同时设置 __pk_strategy__ 和 id_type ，__pk_strategy__优先级更高      │
│    - 仅影响当前模型                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. 全局配置：configure_primary_key(strategy=IdType.XXX)                     │
│    - 在应用启动时设置，影响所有未指定主键规则的模型                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. 默认值：IdType.AUTO_INCREMENT                                            │
│    - 未配置任何策略时使用自增主键                                             │
└─────────────────────────────────────────────────────────────────────────────┘

测试顺序（避免状态污染）：
1. 默认配置测试：在任何全局配置之前定义模型，验证默认使用 AUTO_INCREMENT
2. 全局配置测试：设置全局配置后定义模型，验证全局配置生效
3. 模型级别覆盖测试：模型指定 id_type 或者 __pk_strategy__，验证覆盖全局配置

运行方式：
    python demo_pk_strategy_priority.py
"""

import os
from sqlalchemy import String, inspect as sa_inspect
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

# ==================== 导入依赖 ====================

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    IdType,
    configure_primary_key,
    PrimaryKeyConfig,
    init_versioning,
)


# ==================== 辅助函数 ====================

def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(message: str):
    """打印成功消息"""
    print(f"[✓] {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"[✗] {message}")


def print_info(message: str):
    """打印信息"""
    print(f"[INFO] {message}")


def print_test_result(test_name: str, expected: str, actual: str, passed: bool):
    """打印测试结果"""
    status = "✓ 通过" if passed else "✗ 失败"
    print(f"  {status} - {test_name}")
    print(f"         预期: {expected}")
    print(f"         实际: {actual}")


def get_pk_column_type(model_class) -> str:
    """获取模型主键列的类型描述"""
    mapper = sa_inspect(model_class)
    pk_columns = mapper.primary_key
    if pk_columns:
        pk_col = pk_columns[0]
        col_type = str(pk_col.type)
        return col_type
    return "未知"


def get_pk_value_type(pk_value) -> str:
    """根据主键值判断类型"""
    if pk_value is None:
        return "None"
    if isinstance(pk_value, int):
        if pk_value > 2**31:  # 大于32位整数范围，可能是雪花ID
            return "SNOWFLAKE (BigInteger)"
        return "AUTO_INCREMENT (Integer)"
    if isinstance(pk_value, str):
        if len(pk_value) == 36 and pk_value.count('-') == 4:
            return "UUID (String-36)"
        if len(pk_value) <= 12:
            return f"SHORT_UUID (String-{len(pk_value)})"
        return f"CUSTOM/STRING (String-{len(pk_value)})"
    return f"未知 ({type(pk_value).__name__})"


# ==================== 初始化 ====================

print_section("初始化环境")

# 初始化版本化（可选，但为了完整性）
try:
    init_versioning()
    print_success("版本化功能初始化成功")
except Exception as e:
    print_info(f"版本化已初始化: {e}")


# ==================== 阶段1：默认配置测试 ====================
# 在任何 configure_primary_key 调用之前定义模型

print_section("阶段1：默认配置（未设置任何全局配置）")
print_info(f"当前全局配置: {PrimaryKeyConfig.get_strategy()}")
print_info("预期：使用默认的 AUTO_INCREMENT\n")


class DefaultModel(BaseModel):
    """默认模型 - 在任何全局配置之前定义，应使用默认 AUTO_INCREMENT"""
    __tablename__ = "demo_default_model"
    __table_args__ = {'extend_existing': True}
    # 不设置 __pk_strategy__，使用默认配置
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)


print_success(f"DefaultModel 定义完成，列类型: {get_pk_column_type(DefaultModel)}")


# ==================== 阶段2：全局配置测试 ====================
# 设置全局配置后定义模型

print_section("阶段2：全局配置（设置为 SNOWFLAKE）")

# 设置全局配置为 SNOWFLAKE
configure_primary_key(strategy=IdType.SNOWFLAKE)
print_info(f"全局配置已设置为: {PrimaryKeyConfig.get_strategy()}")
print_info("预期：后续模型使用 SNOWFLAKE\n")


class GlobalSnowflakeModel(BaseModel):
    """全局雪花模型 - 在全局配置设为 SNOWFLAKE 后定义"""
    __tablename__ = "demo_global_snowflake"
    __table_args__ = {'extend_existing': True}
    # 不设置 id_type 或者 __pk_strategy__，使用全局配置 
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)


print_success(f"GlobalSnowflakeModel 定义完成，列类型: {get_pk_column_type(GlobalSnowflakeModel)}")


# ==================== 阶段3：模型级别覆盖测试 ====================
# 模型设置 __pk_strategy__，覆盖全局配置

print_section("阶段3：模型级别覆盖（全局是 SNOWFLAKE，模型指定其他类型）")
print_info(f"当前全局配置: {PrimaryKeyConfig.get_strategy()}")
print_info("预期：模型级别配置优先于全局配置\n")


class OverrideUuidModel(BaseModel):
    """UUID覆盖模型 - 全局是 SNOWFLAKE，但模型指定 UUID"""
    __tablename__ = "demo_override_uuid"
    __table_args__ = {'extend_existing': True}
    id_type = IdType.UUID  # 模型级别覆盖
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)


print_success(f"OverrideUuidModel 定义完成，列类型: {get_pk_column_type(OverrideUuidModel)}")


class OverrideShortUuidModel(BaseModel):
    """短UUID覆盖模型 - 全局是 SNOWFLAKE，但模型指定 SHORT_UUID"""
    __tablename__ = "demo_override_short_uuid"
    __table_args__ = {'extend_existing': True}
    id_type = IdType.SHORT_UUID  # 模型级别覆盖
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)


print_success(f"OverrideShortUuidModel 定义完成，列类型: {get_pk_column_type(OverrideShortUuidModel)}")


class OverrideAutoIncrementModel(BaseModel):
    """自增覆盖模型 - 全局是 SNOWFLAKE，但模型指定 AUTO_INCREMENT"""
    __tablename__ = "demo_override_auto_increment"
    __table_args__ = {'extend_existing': True}
    id_type = IdType.AUTO_INCREMENT  # 模型级别覆盖
    
    title: Mapped[str] = mapped_column(String(200), nullable=True)


print_success(f"OverrideAutoIncrementModel 定义完成，列类型: {get_pk_column_type(OverrideAutoIncrementModel)}")


# ==================== 执行测试 ====================

def run_tests():
    """执行所有测试"""
    print_section("执行测试")
    
    # 初始化数据库
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_pk_strategy_priority.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    # 配置 mappers
    try:
        configure_mappers()
    except Exception:
        pass
    
    # 创建表
    BaseModel.metadata.create_all(engine)
    
    CoreModel.query = session_scope.query_property()
    
    test_results = []
    
    try:
        # ========== 测试1：默认配置 ==========
        print_info("\n测试1: DefaultModel（默认配置 AUTO_INCREMENT）")
        print_info("  模型在任何全局配置之前定义，应使用默认值")
        
        # 恢复到默认配置（与模型定义时一致）
        PrimaryKeyConfig.reset()
        
        obj1 = DefaultModel(name="测试默认", code="DEFAULT001", title="默认配置测试")
        obj1.add(True)
        
        pk_type_1 = get_pk_value_type(obj1.id)
        col_type_1 = get_pk_column_type(DefaultModel)
        
        expected_1 = "AUTO_INCREMENT"
        passed_1 = isinstance(obj1.id, int)
        
        print_test_result(
            "DefaultModel 使用默认配置",
            f"{expected_1} (Integer)",
            f"{pk_type_1}, 列类型: {col_type_1}",
            passed_1
        )
        print_info(f"  生成的ID: {obj1.id}")
        test_results.append(("DefaultModel_默认配置", passed_1))
        
        # ========== 测试2：全局配置 ==========
        print_info("\n测试2: GlobalSnowflakeModel（全局配置 SNOWFLAKE）")
        print_info("  模型在全局配置设为 SNOWFLAKE 后定义")
        
        # 恢复到模型定义时的全局配置（SNOWFLAKE）
        configure_primary_key(strategy=IdType.SNOWFLAKE)
        
        obj2 = GlobalSnowflakeModel(name="测试雪花", code="SNOWFLAKE001", title="全局配置测试")
        obj2.add(True)
        
        pk_type_2 = get_pk_value_type(obj2.id)
        col_type_2 = get_pk_column_type(GlobalSnowflakeModel)
        
        expected_2 = "SNOWFLAKE"
        passed_2 = isinstance(obj2.id, int) and obj2.id > 2**31
        
        print_test_result(
            "GlobalSnowflakeModel 使用全局配置",
            f"{expected_2} (BigInteger)",
            f"{pk_type_2}, 列类型: {col_type_2}",
            passed_2
        )
        print_info(f"  生成的ID: {obj2.id}")
        test_results.append(("GlobalSnowflakeModel_全局配置", passed_2))
        
        # ========== 测试3：模型级别覆盖为 UUID ==========
        print_info("\n测试3: OverrideUuidModel（模型级别 UUID 覆盖全局 SNOWFLAKE）")
        print_info("  模型有 __pk_strategy__=UUID，应忽略全局配置")
        
        # 全局配置仍然是 SNOWFLAKE，但模型级别配置优先
        obj3 = OverrideUuidModel(name="测试UUID", code="UUID001", title="UUID覆盖测试")
        obj3.add(True)
        
        pk_type_3 = get_pk_value_type(obj3.id)
        col_type_3 = get_pk_column_type(OverrideUuidModel)
        
        expected_3 = "UUID"
        passed_3 = isinstance(obj3.id, str) and len(obj3.id) == 36 and obj3.id.count('-') == 4
        
        print_test_result(
            "OverrideUuidModel 模型级别覆盖为 UUID",
            f"{expected_3} (String-36)",
            f"{pk_type_3}, 列类型: {col_type_3}",
            passed_3
        )
        print_info(f"  生成的ID: {obj3.id}")
        test_results.append(("OverrideUuidModel_模型级别覆盖", passed_3))
        
        # ========== 测试4：模型级别覆盖为 SHORT_UUID ==========
        print_info("\n测试4: OverrideShortUuidModel（模型级别 SHORT_UUID 覆盖全局 SNOWFLAKE）")
        print_info("  模型有 __pk_strategy__=SHORT_UUID，应忽略全局配置")
        
        obj4 = OverrideShortUuidModel(name="测试短UUID", code="SHORTUUID001", title="短UUID覆盖测试")
        obj4.add(True)
        
        pk_type_4 = get_pk_value_type(obj4.id)
        col_type_4 = get_pk_column_type(OverrideShortUuidModel)
        
        expected_4 = "SHORT_UUID"
        short_uuid_length = PrimaryKeyConfig.get_short_uuid_length()
        passed_4 = isinstance(obj4.id, str) and len(obj4.id) <= short_uuid_length + 2
        
        print_test_result(
            "OverrideShortUuidModel 模型级别覆盖为 SHORT_UUID",
            f"{expected_4} (String-{short_uuid_length})",
            f"{pk_type_4}, 列类型: {col_type_4}",
            passed_4
        )
        print_info(f"  生成的ID: {obj4.id}")
        test_results.append(("OverrideShortUuidModel_模型级别覆盖", passed_4))
        
        # ========== 测试5：模型级别覆盖为 AUTO_INCREMENT ==========
        print_info("\n测试5: OverrideAutoIncrementModel（模型级别 AUTO_INCREMENT 覆盖全局 SNOWFLAKE）")
        print_info("  模型有 __pk_strategy__=AUTO_INCREMENT，应忽略全局配置")
        
        obj5 = OverrideAutoIncrementModel(name="测试自增", code="AUTOINCR001", title="自增覆盖测试")
        obj5.add(True)
        
        pk_type_5 = get_pk_value_type(obj5.id)
        col_type_5 = get_pk_column_type(OverrideAutoIncrementModel)
        
        expected_5 = "AUTO_INCREMENT"
        passed_5 = isinstance(obj5.id, int)
        
        print_test_result(
            "OverrideAutoIncrementModel 模型级别覆盖为 AUTO_INCREMENT",
            f"{expected_5} (Integer)",
            f"{pk_type_5}, 列类型: {col_type_5}",
            passed_5
        )
        print_info(f"  生成的ID: {obj5.id}")
        test_results.append(("OverrideAutoIncrementModel_模型级别覆盖", passed_5))
        
        # ========== 打印测试总结 ==========
        print_section("测试总结")
        
        all_passed = True
        for test_name, passed in test_results:
            status = "✓ 通过" if passed else "✗ 失败"
            print(f"  {status} - {test_name}")
            if not passed:
                all_passed = False
        
        print()
        if all_passed:
            print_success("所有测试通过！优先级规则验证正确：")
            print_info("  模型级别配置 > 全局配置 > 默认值")
        else:
            print_error("部分测试失败，请检查优先级实现")
        
        # ========== 打印优先级规则验证表格 ==========
        print_section("优先级规则验证")

        
        return all_passed
        
    except Exception as e:
        print_error(f"测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        session_scope.remove()
        print()
        print_info(f"数据库文件: {db_path}")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("  主键策略优先级测试")
    print("  验证：模型级别配置 > 全局配置 > 默认值")
    print("="*70)
    
    success = run_tests()
    
    print()
    if success:
        print_success("优先级规则验证成功！")
    else:
        print_error("优先级规则验证失败！")
    
    return success


if __name__ == "__main__":
    main()
