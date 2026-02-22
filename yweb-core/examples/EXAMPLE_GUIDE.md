# Examples 编写规范

本文档定义了 `yweb-core/examples/` 目录下示例脚本的编写规范，确保所有示例具有一致的测试验证和结果输出。

## 1. 使用 TestCollector

所有示例脚本应使用 `TestCollector` 进行功能验证，提供清晰的测试结果汇总。

### 1.1 导入

```python
from yweb.utils import TestCollector
```

### 1.2 创建实例

```python
tc = TestCollector(title="示例名称")
```

## 2. 验证方法

### 2.1 简单条件检查

```python
# 基本用法
tc.check("测试名称", condition)

# 带自定义错误消息（失败时显示）
tc.check("测试名称", condition, "失败时显示的消息")

# 带调试信息（无论成功失败，失败时都会显示，便于排查）
keys = ['a', 'b', 'c']
tc.check("包含目标键", 'a' in keys, f"实际 keys: {keys}")
```

### 2.2 值相等检查

```python
tc.check_equal("订单号正确", order.order_no, "ORD001")
# 失败时自动显示: 期望 'ORD001', 实际 'xxx'
```

### 2.3 非空检查

```python
tc.check_not_none("订单ID不为空", order.id)
```

### 2.4 真值检查

```python
tc.check_true("列表非空", my_list)
```

### 2.5 可能抛异常的测试

当测试可能抛出异常时，使用 `run_test` 包装，避免中断后续测试：

```python
def check_order_relation():
    assert hasattr(item, 'order'), "缺少 order 属性"
    assert item.order == order, f"期望 order={order.id}"

tc.run_test("订单项反向关系正确", check_order_relation)
```

### 2.6 条件分支中的测试

当测试依赖于前置条件时，使用 if-else 分支：

```python
if some_object and hasattr(some_object, 'table'):
    tc.check_not_none("表存在", some_object.table)
    tc.check("列类型正确", some_object.table.c.id.type is not None)
else:
    # 前置条件不满足，记录失败
    tc.check("对象已初始化", False, f"对象状态: {some_object}")
```

## 3. 分节标题

使用 `section()` 将测试分组，便于阅读：

```python
tc.section("1. 创建数据")
# ... 创建相关的测试 ...

tc.section("2. 查询验证")
# ... 查询相关的测试 ...

tc.section("3. 修改数据")
# ... 修改相关的测试 ...
```

## 4. 输出汇总

在脚本末尾调用 `summary()` 输出测试汇总：

```python
# 返回 bool: True 表示全部通过，False 表示有失败
return tc.summary()
```

## 5. 测试命名建议

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 创建验证 | `xxx创建成功` / `xxxID不为空` | `订单创建成功`、`模型ID不为空` |
| 值验证 | `xxx正确` / `xxx为xxx` | `订单号正确`、`ID类型为字符串` |
| 状态验证 | `xxx已xxx` | `配置已加载`、`表已创建` |
| 关系验证 | `xxx指向xxx` / `xxx包含xxx` | `外键指向订单`、`订单包含2个商品` |
| 数量验证 | `xxx数量为N` / `共有N个xxx` | `订单项数量为2`、`共有3个订单` |

## 6. 完整示例模板

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
示例标题

本脚本用于演示/测试 xxx 功能，验证：
- 功能点1
- 功能点2
- 功能点3
"""

from yweb.utils import TestCollector
# ... 其他导入 ...


def main():
    """主函数"""
    tc = TestCollector(title="示例名称")
    
    # 如果需要数据库，在这里声明以便 finally 中清理
    session_scope = None
    
    try:
        # ============================================================
        # 1. 初始化/配置
        # ============================================================
        tc.section("1. 初始化配置")
        
        # 配置操作...
        tc.check("配置完成", True)
        
        # ============================================================
        # 2. 核心功能测试
        # ============================================================
        tc.section("2. 核心功能测试")
        
        result = some_operation()
        
        tc.check_not_none("结果不为空", result)
        tc.check_equal("结果值正确", result.value, expected_value)
        
        # 条件分支测试
        if result.has_detail:
            tc.check("详情数据正确", result.detail is not None)
        else:
            tc.check("有详情数据", False, "详情为空")
        
        # ============================================================
        # 3. 异常场景测试
        # ============================================================
        tc.section("3. 异常场景测试")
        
        def check_edge_case():
            assert condition, "错误描述"
        
        tc.run_test("边界情况处理正确", check_edge_case)
        
    except Exception as e:
        print(f"\n发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源（如数据库连接）
        if session_scope:
            session_scope.remove()
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    main()
```

## 7. 输出效果示例

运行示例脚本后，输出效果如下：

```
--- 1. 创建订单和订单项 ---
  ✅ 订单创建后ID不为空
  ✅ 订单号正确
  ✅ 订单总金额正确
  ✅ 订单项1的ID不为空
  ✅ 订单项2的ID不为空

--- 2. 查询验证关系 ---
  ✅ 能够查询到订单
  ❌ 订单项1的order属性指向正确的订单: OrderItemModel 没有 order 属性

============================================================
ORM 外键关系演示 - 测试汇总
============================================================
  总数: 32  |  通过: 30  |  失败: 2  ❌

失败的测试:
  [FAIL] 订单项1的order属性指向正确的订单
         OrderItemModel 没有 order 属性
  [FAIL] 订单项2的order属性指向正确的订单
         OrderItemModel 没有 order 属性
============================================================
```

## 8. API 速查表

| 方法 | 用途 | 示例 |
|------|------|------|
| `check(name, cond)` | 条件检查 | `tc.check("非空", x is not None)` |
| `check(name, cond, msg)` | 带调试信息的检查 | `tc.check("包含键", 'a' in keys, f"keys={keys}")` |
| `check_equal(name, actual, expected)` | 相等检查 | `tc.check_equal("ID", obj.id, 1)` |
| `check_not_none(name, value)` | 非空检查 | `tc.check_not_none("ID", obj.id)` |
| `check_true(name, value)` | 真值检查 | `tc.check_true("有数据", items)` |
| `run_test(name, func)` | 运行可能抛异常的测试 | `tc.run_test("检查", check_func)` |
| `section(title)` | 分节标题 | `tc.section("1. 创建")` |
| `summary()` | 输出汇总并返回结果 | `return tc.summary()` |
| `reset()` | 重置所有测试结果 | `tc.reset()` |

## 9. 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `tc.total` | int | 总测试数 |
| `tc.passed_count` | int | 通过数 |
| `tc.failed_count` | int | 失败数 |
| `tc.all_passed` | bool | 是否全部通过 |
| `tc.failed_results` | list | 失败的测试结果列表 |
| `tc.verbose` | bool | 是否实时打印结果（默认 True） |

## 10. 最佳实践

1. **测试名称要有描述性** - 看名称就知道测试什么
2. **善用第三个参数** - 添加调试信息，便于排查问题
3. **用 `run_test` 包装可能抛异常的代码** - 避免一个失败中断所有测试
4. **合理使用 section 分组** - 按功能模块划分，建议用数字编号
5. **finally 中清理资源** - 确保数据库连接等资源被正确释放
6. **条件分支记录失败** - 前置条件不满足时，用 `tc.check(..., False, ...)` 记录
