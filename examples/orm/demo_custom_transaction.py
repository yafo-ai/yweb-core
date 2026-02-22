"""自定义 Transaction 表演示（索引文件）

本脚本演示了 sqlalchemy-history 的 Transaction 表自定义功能：
1. 自定义 Transaction 表名
2. 为不同的模型创建不同的 Transaction 表
3. 自定义 Transaction 表的字段
4. 使用 yweb.orm 集成自定义 Transaction

================================================================================
                          Transaction 表概述
================================================================================

Transaction 表用于记录每次数据库操作的事务信息，版本历史表通过 transaction_id 
关联到 Transaction 表，从而追踪每次变更的上下文信息。

默认 Transaction 表结构：
┌─────────────────────────────────────────────────────────────────────────────┐
│ id          - 事务ID（主键，自增）                                          │
│ issued_at   - 事务发生时间                                                  │
│ remote_addr - 远程地址（可选，默认启用）                                    │
│ user_id     - 操作用户ID（可选，需配置 user_cls）                           │
└─────────────────────────────────────────────────────────────────────────────┘

自定义场景：
1. 自定义表名：适合多租户系统或需要区分不同模块的审计日志
2. 分离 Transaction 表：不同业务模块的历史记录使用独立的事务表
3. 扩展字段：添加业务相关的元数据（如请求ID、操作原因等）
4. yweb.orm 集成：在 yweb.orm 框架中使用自定义 Transaction 表

================================================================================
                          重要说明
================================================================================

由于 make_versioned() 是全局的，每个场景必须独立运行，否则会产生冲突。

推荐运行方式：

方式1：运行本文件（推荐）
    本文件会通过创建独立的 Python 进程来顺序运行所有场景，
    每个场景在独立进程中运行，避免 make_versioned() 全局状态冲突。
    
    python demo_custom_transaction.py

方式2：单独运行每个场景（也推荐）
    cd demo_custom_transaction
    python demo_custom_transaction_scenario1.py  # 场景1：自定义表名
    python demo_custom_transaction_scenario2.py  # 场景2：分离Transaction表
    python demo_custom_transaction_scenario3.py  # 场景3：扩展字段
    python demo_custom_transaction_scenario4.py  # 场景4：yweb集成
"""

"""
    配置示例代码
    from yweb.orm import init_versioning
    from sqlalchemy_history.transaction import TransactionBase
    
    # 定义自定义 Transaction 类
    class MyTransaction(Base, TransactionBase):
        __tablename__ = "my_audit_log"
        
        id = Column(BigInteger, primary_key=True, autoincrement=True)
        remote_addr = Column(String(50))
        request_id = Column(String(64))
        # 添加更多自定义字段...
    
    # 在应用启动时初始化
    init_versioning(transaction_cls=MyTransaction)
"""

import os
import sys
import subprocess

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


# ==================== 主函数 ====================

def run_scenario_script(script_name: str, scenario_name: str) -> bool:
    """在独立进程中运行场景脚本
    
    Args:
        script_name: 脚本文件名（如 'demo_custom_transaction_scenario1.py'）
        scenario_name: 场景名称（用于显示）
    
    Returns:
        bool: 是否成功运行（返回码为0表示成功）
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 脚本文件在 demo_custom_transaction 子文件夹下
    script_path = os.path.join(script_dir, "demo_custom_transaction", script_name)
    
    if not os.path.exists(script_path):
        print_error(f"脚本文件不存在: {script_path}")
        return False
    
    print_section(f"运行 {scenario_name}")
    print_info(f"执行脚本: {script_name}")
    print_info(f"使用独立进程运行，避免 make_versioned 全局状态冲突\n")
    
    try:
        # 使用当前 Python 解释器运行脚本
        # 设置工作目录为脚本所在目录（demo_custom_transaction 子文件夹）
        script_subdir = os.path.join(script_dir, "demo_custom_transaction")
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=script_subdir,  # 工作目录设置为脚本所在子文件夹
            capture_output=False,  # 实时显示输出
            text=True,
            check=False  # 不抛出异常，手动检查返回码
        )
        
        success = result.returncode == 0
        if success:
            print_success(f"{scenario_name} 运行成功")
        else:
            print_error(f"{scenario_name} 运行失败，返回码: {result.returncode}")
        
        return success
        
    except Exception as e:
        print_error(f"运行 {scenario_name} 时发生异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数
    
    通过创建独立的 Python 进程来顺序运行各个场景脚本，
    避免 make_versioned() 全局状态冲突。
    """
    print("\n" + "="*70)
    print("  自定义 Transaction 表演示（索引文件）")
    print("="*70)
    
    print()
    print_info("本脚本将通过创建独立的 Python 进程来运行各个场景，")
    print_info("每个场景在独立的进程中运行，避免 make_versioned() 全局状态冲突。\n")
    
    # 定义场景配置
    scenarios = [
        ("demo_custom_transaction_scenario1.py", "场景1：自定义 Transaction 表名"),
        ("demo_custom_transaction_scenario2.py", "场景2：不同模型使用不同的 Transaction 表"),
        ("demo_custom_transaction_scenario3.py", "场景3：扩展 Transaction 表字段"),
        ("demo_custom_transaction_scenario4.py", "场景4：使用 yweb.orm 集成自定义 Transaction"),
    ]
    
    results = {}
    
    # 顺序运行每个场景
    for script_name, scenario_name in scenarios:
        success = run_scenario_script(script_name, scenario_name)
        results[scenario_name] = success
        print()  # 场景之间添加空行
    
    # 打印总结
    print_section("演示总结")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    for name, passed_flag in results.items():
        status = "✓ 通过" if passed_flag else "✗ 失败"
        print(f"  {status} - {name}")
    
    print()
    print_info(f"总计: {total} 个场景，通过: {passed}，失败: {failed}")
    
    print()
    print_info("重要说明：")
    print_info("1. 每个场景在独立的 Python 进程中运行，避免了 make_versioned() 全局状态冲突")
    print_info("2. 由于make_versioned() 多次调用会出错，所以初始化版本化 建议使用 init_versioning() 而不是原生的 make_versioned()")
    print_info("3. 所有版本化模型共享同一个 Transaction 表")
    print_info("4. 如需分离 Transaction 表，考虑使用不同的数据库或 schema")
    print_info("5. 扩展字段可以通过中间件或事件监听器自动填充")
    print()

if __name__ == "__main__":
    main()
