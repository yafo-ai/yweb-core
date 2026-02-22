"""配置加载器测试

测试 YAML 配置加载和配置管理功能
"""

import pytest
import os

from yweb.config import (
    ConfigLoader,
    ConfigManager,
    load_yaml_config,
    load_env_file,
    set_env_from_file,
    YAML_AVAILABLE,
)


@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestConfigLoader:
    """ConfigLoader 测试"""
    
    def test_load_yaml_config(self, sample_yaml_config):
        """测试加载 YAML 配置"""
        config = ConfigLoader.load(sample_yaml_config, use_cache=False)
        
        assert config is not None
        assert config["app_name"] == "Test Application"
        assert config["debug"] == True
        assert config["database"]["url"] == "sqlite:///test.db"
    
    def test_config_caching(self, sample_yaml_config):
        """测试配置缓存"""
        # 清除缓存
        ConfigLoader.clear_cache()
        
        # 第一次加载
        config1 = ConfigLoader.load(sample_yaml_config, use_cache=True)
        
        # 第二次加载（应该从缓存获取）
        config2 = ConfigLoader.load(sample_yaml_config, use_cache=True)
        
        assert config1 is config2  # 应该是同一个对象
        
        # 验证缓存路径
        cached_paths = ConfigLoader.get_cached_paths()
        assert len(cached_paths) > 0
    
    def test_reload_config(self, sample_yaml_config):
        """测试重新加载配置"""
        # 先加载一次
        ConfigLoader.load(sample_yaml_config, use_cache=True)
        
        # 重新加载
        config = ConfigLoader.reload(sample_yaml_config)
        
        assert config is not None
        assert config["app_name"] == "Test Application"

    def test_cache_does_not_auto_refresh_until_reload(self, temp_file):
        """测试缓存不会自动刷新，需显式 reload"""
        path = temp_file("settings.yaml", "app_name: v1")
        ConfigLoader.clear_cache()

        config_v1 = ConfigLoader.load(path, use_cache=True)
        assert config_v1["app_name"] == "v1"

        # 修改文件内容，但继续走缓存
        with open(path, "w", encoding="utf-8") as f:
            f.write("app_name: v2\n")
        cached_again = ConfigLoader.load(path, use_cache=True)
        assert cached_again["app_name"] == "v1"

        # 显式 reload 后应读取新内容
        reloaded = ConfigLoader.reload(path)
        assert reloaded["app_name"] == "v2"
    
    def test_clear_cache(self, sample_yaml_config):
        """测试清除缓存"""
        ConfigLoader.load(sample_yaml_config, use_cache=True)
        
        ConfigLoader.clear_cache()
        
        assert len(ConfigLoader.get_cached_paths()) == 0
    
    def test_load_nonexistent_file(self, temp_dir):
        """测试加载不存在的文件"""
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(
                os.path.join(temp_dir, "nonexistent.yaml"),
                use_cache=False
            )
    
    def test_load_with_base_dir(self, temp_file, temp_dir):
        """测试使用基础目录加载"""
        # 创建子目录中的配置文件
        config_content = "app_name: Base Dir Test"
        temp_file("subdir/config.yaml", config_content)
        
        config = ConfigLoader.load(
            "subdir/config.yaml",
            base_dir=temp_dir,
            use_cache=False
        )
        
        assert config["app_name"] == "Base Dir Test"


@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestConfigManager:
    """ConfigManager 测试"""
    
    def test_create_config_manager(self, temp_dir):
        """测试创建配置管理器"""
        manager = ConfigManager(base_dir=temp_dir)
        
        assert manager.base_dir == temp_dir
    
    def test_load_config(self, temp_dir, temp_file):
        """测试加载配置"""
        temp_file("settings.yaml", "app_name: Manager Test\ndebug: true")
        
        manager = ConfigManager(base_dir=temp_dir)
        config = manager.load("settings.yaml")
        
        assert config["app_name"] == "Manager Test"
        assert config["debug"] == True
    
    def test_merge_config(self, temp_dir, temp_file):
        """测试合并配置"""
        temp_file("base.yaml", "app_name: Base\nlevel: 1\nfeature_a: true")
        temp_file("override.yaml", "level: 2\nfeature_b: true")
        
        manager = ConfigManager(base_dir=temp_dir)
        manager.load("base.yaml")
        manager.load("override.yaml", merge=True)
        
        config = manager.to_dict()
        
        assert config["app_name"] == "Base"  # 未被覆盖
        assert config["level"] == 2  # 被覆盖
        assert config["feature_a"] == True  # 保留
        assert config["feature_b"] == True  # 新增
    
    def test_get_nested_value(self, temp_dir, temp_file):
        """测试获取嵌套配置值"""
        yaml_content = """
database:
  url: "sqlite:///test.db"
  pool:
    size: 10
    overflow: 5
"""
        temp_file("nested.yaml", yaml_content)
        
        manager = ConfigManager(base_dir=temp_dir)
        manager.load("nested.yaml")
        
        assert manager.get("database.url") == "sqlite:///test.db"
        assert manager.get("database.pool.size") == 10
        assert manager.get("database.pool.overflow") == 5
        assert manager.get("nonexistent.key", "default") == "default"
    
    def test_set_nested_value(self, temp_dir, temp_file):
        """测试设置嵌套配置值"""
        temp_file("empty.yaml", "{}")
        
        manager = ConfigManager(base_dir=temp_dir)
        manager.load("empty.yaml")
        
        manager.set("database.url", "sqlite:///new.db")
        manager.set("database.pool.size", 20)
        
        assert manager.get("database.url") == "sqlite:///new.db"
        assert manager.get("database.pool.size") == 20

    def test_merge_deep_nested_config(self, temp_dir, temp_file):
        """测试深层嵌套配置合并不丢失兄弟节点"""
        # 避免复用同名文件触发全局缓存污染，保证测试隔离
        ConfigLoader.clear_cache()
        temp_file(
            "base.yaml",
            "database:\n  pool:\n    size: 10\n    timeout: 30\n  url: sqlite:///base.db\n",
        )
        temp_file(
            "override.yaml",
            "database:\n  pool:\n    size: 20\n",
        )

        manager = ConfigManager(base_dir=temp_dir)
        manager.load("base.yaml")
        manager.load("override.yaml", merge=True)

        assert manager.get("database.pool.size") == 20
        assert manager.get("database.pool.timeout") == 30
        assert manager.get("database.url") == "sqlite:///base.db"

    def test_get_returns_default_when_path_hits_non_dict(self, temp_dir, temp_file):
        """测试路径中间节点非 dict 时返回默认值"""
        temp_file("scalar.yaml", "database: sqlite:///only-string.db")

        manager = ConfigManager(base_dir=temp_dir)
        manager.load("scalar.yaml")

        assert manager.get("database.pool.size", 99) == 99


class TestLoadEnvFile:
    """load_env_file 函数测试"""
    
    def test_load_env_file(self, sample_env_file):
        """测试加载 .env 文件"""
        env_vars = load_env_file(sample_env_file)
        
        assert env_vars["YWEB_APP_NAME"] == "Test App"
        assert env_vars["YWEB_DEBUG"] == "true"
        assert env_vars["YWEB_DATABASE_URL"] == "sqlite:///test.db"
    
    def test_load_nonexistent_env_file(self, temp_dir):
        """测试加载不存在的 .env 文件"""
        env_vars = load_env_file(os.path.join(temp_dir, ".env"))
        
        assert env_vars == {}
    
    def test_env_file_with_quotes(self, temp_file):
        """测试带引号的 .env 文件"""
        env_content = '''
SINGLE_QUOTED='single quoted value'
DOUBLE_QUOTED="double quoted value"
NO_QUOTES=no quotes value
'''
        env_path = temp_file(".env.quotes", env_content)
        
        env_vars = load_env_file(env_path)
        
        assert env_vars["SINGLE_QUOTED"] == "single quoted value"
        assert env_vars["DOUBLE_QUOTED"] == "double quoted value"
        assert env_vars["NO_QUOTES"] == "no quotes value"
    
    def test_env_file_with_comments(self, temp_file):
        """测试带注释的 .env 文件"""
        env_content = '''
# This is a comment
APP_NAME=Test

# Another comment
DEBUG=true
'''
        env_path = temp_file(".env.comments", env_content)
        
        env_vars = load_env_file(env_path)
        
        assert "APP_NAME" in env_vars
        assert "DEBUG" in env_vars
        assert len(env_vars) == 2  # 只有两个有效的变量


class TestSetEnvFromFile:
    """set_env_from_file 函数测试"""
    
    def test_set_env_from_file(self, temp_file):
        """测试从文件设置环境变量"""
        env_content = "TEST_VAR_SET=test_value"
        env_path = temp_file(".env.set", env_content)
        
        # 确保环境变量不存在
        if "TEST_VAR_SET" in os.environ:
            del os.environ["TEST_VAR_SET"]
        
        set_env_from_file(env_path)
        
        try:
            assert os.environ.get("TEST_VAR_SET") == "test_value"
        finally:
            # 清理
            if "TEST_VAR_SET" in os.environ:
                del os.environ["TEST_VAR_SET"]
    
    def test_set_env_no_override(self, temp_file):
        """测试不覆盖已存在的环境变量"""
        env_content = "EXISTING_VAR=new_value"
        env_path = temp_file(".env.no_override", env_content)
        
        # 设置已存在的环境变量
        os.environ["EXISTING_VAR"] = "original_value"
        
        try:
            set_env_from_file(env_path, override=False)
            assert os.environ["EXISTING_VAR"] == "original_value"
        finally:
            del os.environ["EXISTING_VAR"]
    
    def test_set_env_with_override(self, temp_file):
        """测试覆盖已存在的环境变量"""
        env_content = "OVERRIDE_VAR=new_value"
        env_path = temp_file(".env.override", env_content)
        
        # 设置已存在的环境变量
        os.environ["OVERRIDE_VAR"] = "original_value"
        
        try:
            set_env_from_file(env_path, override=True)
            assert os.environ["OVERRIDE_VAR"] == "new_value"
        finally:
            del os.environ["OVERRIDE_VAR"]


@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestLoadYamlConfig:
    """load_yaml_config 函数测试"""
    
    def test_load_yaml_config_with_settings(self, sample_yaml_config):
        """测试加载 YAML 配置到 Settings"""
        from pydantic_settings import BaseSettings
        
        class TestSettings(BaseSettings):
            app_name: str = ""
            debug: bool = False
            
            model_config = {"extra": "ignore"}
        
        settings = load_yaml_config(sample_yaml_config, TestSettings)
        
        assert settings.app_name == "Test Application"
        assert settings.debug == True
    
    def test_load_yaml_config_with_overrides(self, sample_yaml_config):
        """测试加载 YAML 配置并覆盖"""
        from pydantic_settings import BaseSettings
        
        class TestSettings(BaseSettings):
            app_name: str = ""
            debug: bool = False
            
            model_config = {"extra": "ignore"}
        
        settings = load_yaml_config(
            sample_yaml_config,
            TestSettings,
            app_name="Overridden Name"
        )
        
        assert settings.app_name == "Overridden Name"
        assert settings.debug == True  # 来自 YAML

