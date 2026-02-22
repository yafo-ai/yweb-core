#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
轻量级测试收集器

提供类似单元测试的功能，但更轻量，适合用于演示脚本中验证功能是否正常。

功能：
- 运行测试并记录结果（通过/失败）
- 捕获异常，不中断后续测试
- 最终输出汇总报告

使用示例：
    from test_collector import TestCollector
    
    tc = TestCollector("订单模块测试")
    
    # 方式1：使用 run_test 运行测试函数
    tc.run_test("订单创建", lambda: assert order.id is not None)
    
    # 方式2：使用 check 进行简单断言
    tc.check("订单号正确", order.order_no == "ORD001")
    tc.check("总金额正确", order.total == 100, f"期望 100, 实际 {order.total}")
    
    # 输出汇总
    tc.summary()
"""

from typing import Callable, Optional, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class TestStatus(Enum):
    """测试状态"""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


# 使用 ASCII 兼容的符号（避免 Windows 控制台编码问题）
SYMBOL_PASS = "✅"
SYMBOL_FAIL = "❌"
SYMBOL_OK = "✅"
SYMBOL_NG = "❌"


@dataclass
class TestResult:
    """单个测试结果"""
    name: str
    status: TestStatus
    message: Optional[str] = None
    
    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASSED


@dataclass
class TestCollector:
    """轻量级测试收集器"""
    
    title: str = "测试"
    results: List[TestResult] = field(default_factory=list)
    verbose: bool = True  # 是否实时打印每个测试结果
    
    def run_test(self, test_name: str, test_func: Callable, *args, **kwargs) -> bool:
        """
        运行单个测试函数并记录结果
        
        Args:
            test_name: 测试名称
            test_func: 测试函数，应该在失败时抛出 AssertionError
            *args, **kwargs: 传递给测试函数的参数
            
        Returns:
            bool: 测试是否通过
        """
        try:
            test_func(*args, **kwargs)
            result = TestResult(test_name, TestStatus.PASSED)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_PASS} {test_name}")
            return True
        except AssertionError as e:
            msg = str(e) if str(e) else "断言失败"
            result = TestResult(test_name, TestStatus.FAILED, msg)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_FAIL} {test_name}: {msg}")
            return False
        except Exception as e:
            msg = f"异常: {type(e).__name__}: {e}"
            result = TestResult(test_name, TestStatus.ERROR, msg)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_FAIL} {test_name}: {msg}")
            return False
    
    def check(self, test_name: str, condition: bool, message: str = None) -> bool:
        """
        检查条件是否为真
        
        Args:
            test_name: 测试名称
            condition: 要检查的条件
            message: 失败时的消息（可选）
            
        Returns:
            bool: 测试是否通过
        """
        if condition:
            result = TestResult(test_name, TestStatus.PASSED)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_PASS} {test_name}")
            return True
        else:
            msg = message or "条件不满足"
            result = TestResult(test_name, TestStatus.FAILED, msg)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_FAIL} {test_name}: {msg}")
            return False
    
    def check_equal(self, test_name: str, actual: Any, expected: Any) -> bool:
        """
        检查两个值是否相等
        
        Args:
            test_name: 测试名称
            actual: 实际值
            expected: 期望值
            
        Returns:
            bool: 测试是否通过
        """
        if actual == expected:
            result = TestResult(test_name, TestStatus.PASSED)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_PASS} {test_name}")
            return True
        else:
            msg = f"期望 {expected!r}, 实际 {actual!r}"
            result = TestResult(test_name, TestStatus.FAILED, msg)
            self.results.append(result)
            if self.verbose:
                print(f"  {SYMBOL_FAIL} {test_name}: {msg}")
            return False
    
    def check_not_none(self, test_name: str, value: Any) -> bool:
        """
        检查值是否不为 None
        
        Args:
            test_name: 测试名称
            value: 要检查的值
            
        Returns:
            bool: 测试是否通过
        """
        return self.check(test_name, value is not None, f"值为 None")
    
    def check_true(self, test_name: str, value: Any) -> bool:
        """
        检查值是否为真
        
        Args:
            test_name: 测试名称
            value: 要检查的值
            
        Returns:
            bool: 测试是否通过
        """
        return self.check(test_name, bool(value), f"值为假: {value!r}")
    
    def section(self, title: str):
        """打印测试分节标题"""
        print(f"\n--- {title} ---")
    
    @property
    def total(self) -> int:
        """总测试数"""
        return len(self.results)
    
    @property
    def passed_count(self) -> int:
        """通过的测试数"""
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed_count(self) -> int:
        """失败的测试数"""
        return self.total - self.passed_count
    
    @property
    def failed_results(self) -> List[TestResult]:
        """所有失败的测试结果"""
        return [r for r in self.results if not r.passed]
    
    @property
    def all_passed(self) -> bool:
        """是否所有测试都通过"""
        return self.failed_count == 0
    
    def summary(self) -> bool:
        """
        打印测试汇总报告
        
        Returns:
            bool: 是否所有测试都通过
        """
        width = 60
        
        print()
        print("=" * width)
        print(f"{self.title} - 测试汇总")
        print("=" * width)
        
        # 统计信息
        status_icon = SYMBOL_OK if self.all_passed else SYMBOL_NG
        print(f"  总数: {self.total}  |  通过: {self.passed_count}  |  失败: {self.failed_count}  {status_icon}")
        
        # 失败详情
        if self.failed_count > 0:
            print()
            print("失败的测试:")
            for result in self.failed_results:
                status = "FAIL" if result.status == TestStatus.FAILED else "ERROR"
                print(f"  [{status}] {result.name}")
                if result.message:
                    print(f"         {result.message}")
        
        print("=" * width)
        
        return self.all_passed
    
    def reset(self):
        """重置所有测试结果"""
        self.results.clear()


# 便捷函数：创建测试收集器
def create_test_collector(title: str = "测试", verbose: bool = True) -> TestCollector:
    """
    创建测试收集器的便捷函数
    
    Args:
        title: 测试标题
        verbose: 是否实时打印结果
        
    Returns:
        TestCollector: 测试收集器实例
    """
    return TestCollector(title=title, verbose=verbose)
