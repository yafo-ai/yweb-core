"""get_logger 功能测试

测试自动推断模块名的日志记录器获取功能
"""

import pytest
import logging


class TestGetLoggerAutoInfer:
    """测试 get_logger 自动推断功能"""
    
    def test_auto_infer_module_name(self):
        """测试无参数调用时自动推断模块名"""
        from yweb.log import get_logger
        
        logger = get_logger()
        
        assert logger is not None
        # 在当前测试模块中调用，应该得到测试模块的名称
        assert logger.name == __name__
    
    def test_auto_infer_returns_same_logger(self):
        """测试多次调用返回相同的 logger 实例"""
        from yweb.log import get_logger
        
        logger1 = get_logger()
        logger2 = get_logger()
        
        # logging.getLogger 对相同名称返回相同实例
        assert logger1 is logger2


class TestGetLoggerWithName:
    """测试 get_logger 显式指定名称功能"""
    
    def test_simple_name_adds_prefix(self):
        """测试简单名称自动添加 yweb 前缀"""
        from yweb.log import get_logger
        
        logger = get_logger("api")
        
        assert logger.name == "yweb.api"
    
    def test_nested_name_adds_prefix(self):
        """测试嵌套名称（不含点号）自动添加前缀"""
        from yweb.log import get_logger
        
        # 注意：orm_transaction 没有点号，会被视为简单名称
        logger = get_logger("orm")
        
        assert logger.name == "yweb.orm"
    
    def test_yweb_prefix_not_duplicated(self):
        """测试已有 yweb 前缀不重复添加"""
        from yweb.log import get_logger
        
        logger1 = get_logger("yweb.custom")
        logger2 = get_logger("yweb.orm.transaction")
        
        assert logger1.name == "yweb.custom"
        assert logger2.name == "yweb.orm.transaction"
    
    def test_yweb_alone_not_modified(self):
        """测试单独的 yweb 名称不修改"""
        from yweb.log import get_logger
        
        logger = get_logger("yweb")
        
        assert logger.name == "yweb"
    
    def test_external_module_no_prefix(self):
        """测试外部模块名（含点号）不添加前缀"""
        from yweb.log import get_logger
        
        # 包含点号的名称被视为外部模块，不添加 yweb 前缀
        logger1 = get_logger("sqlalchemy.engine")
        logger2 = get_logger("uvicorn.access")
        logger3 = get_logger("fastapi.routing")
        
        assert logger1.name == "sqlalchemy.engine"
        assert logger2.name == "uvicorn.access"
        assert logger3.name == "fastapi.routing"
    
    def test_dotted_yweb_path(self):
        """测试点号分隔的 yweb 路径"""
        from yweb.log import get_logger
        
        # 已经包含点号且以 yweb 开头，不修改
        logger = get_logger("yweb.middleware.request_logging")
        
        assert logger.name == "yweb.middleware.request_logging"


class TestGetLoggerBackwardsCompatibility:
    """测试向后兼容性"""
    
    def test_predefined_loggers_exist(self):
        """测试预定义的日志记录器存在"""
        from yweb.log import (
            api_logger,
            auth_logger,
            sql_logger,
            orm_logger,
            transaction_logger,
            logger,
        )
        
        assert api_logger is not None
        assert auth_logger is not None
        assert sql_logger is not None
        assert orm_logger is not None
        assert transaction_logger is not None
        assert logger is not None
    
    def test_predefined_loggers_names(self):
        """测试预定义日志记录器的名称"""
        from yweb.log import (
            api_logger,
            auth_logger,
            sql_logger,
            orm_logger,
            transaction_logger,
        )
        
        assert api_logger.name == "yweb.api"
        assert auth_logger.name == "yweb.auth"
        assert sql_logger.name == "yweb.sql"
        assert orm_logger.name == "yweb.orm"
        assert transaction_logger.name == "yweb.orm.transaction"
    
    def test_root_logger(self):
        """测试根日志记录器"""
        from yweb.log import logger
        
        assert logger.name == "yweb"


class TestGetLoggerHierarchy:
    """测试日志记录器层级关系"""
    
    def test_logger_hierarchy(self):
        """测试日志记录器层级继承"""
        from yweb.log import get_logger
        
        # 创建层级日志器
        parent = get_logger("yweb")
        child = get_logger("yweb.orm")
        grandchild = get_logger("yweb.orm.transaction")
        
        # 验证层级关系
        assert child.parent == parent or child.parent.name == parent.name
        assert grandchild.parent == child or grandchild.parent.name == child.name
    
    def test_logger_propagation(self):
        """测试日志传播"""
        import io
        
        # 直接使用 logging.getLogger 创建父子日志器，避免 get_logger 的前缀处理
        parent = logging.getLogger("test_propagation_parent")
        child = logging.getLogger("test_propagation_parent.child")
        
        # 在父日志器上添加处理器
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))
        parent.addHandler(handler)
        parent.setLevel(logging.DEBUG)
        
        # 子日志器写入日志
        child.setLevel(logging.DEBUG)
        child.info("test message")
        
        # 验证日志传播到父日志器
        output = stream.getvalue()
        assert "test_propagation_parent.child" in output
        assert "test message" in output
        
        # 清理
        parent.removeHandler(handler)


class TestGetLoggerEdgeCases:
    """测试边界情况"""
    
    def test_empty_string_name(self):
        """测试空字符串名称"""
        from yweb.log import get_logger
        
        # 空字符串应该添加前缀
        logger = get_logger("")
        
        # 空字符串 + yweb 前缀 = "yweb."
        assert logger.name == "yweb."
    
    def test_whitespace_name(self):
        """测试空白字符名称"""
        from yweb.log import get_logger
        
        # 空白字符串也会添加前缀
        logger = get_logger("  ")
        
        assert logger.name == "yweb.  "
    
    def test_special_characters(self):
        """测试特殊字符名称"""
        from yweb.log import get_logger
        
        # 下划线不含点号，会添加前缀
        logger = get_logger("my_module")
        assert logger.name == "yweb.my_module"
        
        # 连字符同样
        logger2 = get_logger("my-module")
        assert logger2.name == "yweb.my-module"


class TestGetLoggerIntegration:
    """集成测试"""
    
    def test_logger_can_log(self):
        """测试日志记录器可以正常记录日志"""
        from yweb.log import get_logger
        import io
        
        logger = get_logger("integration_test")
        
        # 添加测试处理器
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # 记录各级别日志
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        
        output = stream.getvalue()
        
        assert "DEBUG - debug message" in output
        assert "INFO - info message" in output
        assert "WARNING - warning message" in output
        assert "ERROR - error message" in output
        
        # 清理
        logger.removeHandler(handler)
    
    def test_auto_infer_in_function(self):
        """测试在函数内部自动推断"""
        from yweb.log import get_logger
        
        def inner_function():
            return get_logger()
        
        logger = inner_function()
        
        # 应该得到当前模块的名称
        assert logger.name == __name__
    
    def test_auto_infer_in_class_method(self):
        """测试在类方法内部自动推断"""
        from yweb.log import get_logger
        
        class TestClass:
            def get_class_logger(self):
                return get_logger()
        
        obj = TestClass()
        logger = obj.get_class_logger()
        
        # 应该得到当前模块的名称
        assert logger.name == __name__
