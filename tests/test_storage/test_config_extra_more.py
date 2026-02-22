"""storage.config 额外分支覆盖测试（新文件）"""

import os
import tempfile

import pytest

from yweb.storage.config import (
    LocalStorageConfig,
    MemoryStorageConfig,
    OSSStorageConfig,
    S3StorageConfig,
    SecureURLConfig,
    StorageConfig,
    resolve_env_var,
    validate_config,
)


class TestStorageConfigExtraMore:
    def test_resolve_env_var_paths(self, monkeypatch):
        monkeypatch.setenv("YWEB_CFG_X", "resolved-value")
        assert resolve_env_var("${YWEB_CFG_X}") == "resolved-value"
        assert resolve_env_var("plain-value") == "plain-value"

        with pytest.raises(ValueError):
            resolve_env_var("${YWEB_CFG_MISSING}")

    def test_memory_config_max_size_limit(self):
        with pytest.raises(ValueError):
            MemoryStorageConfig(type="memory", max_size=11 * 1024 * 1024 * 1024)

    def test_local_config_base_path_and_accessibility(self, monkeypatch):
        # 绝对路径校验失败
        with pytest.raises(ValueError):
            LocalStorageConfig(type="local", base_path="relative/path")

        # 使用环境变量展开
        temp_dir = tempfile.gettempdir()
        monkeypatch.setenv("YWEB_LOCAL_PATH", temp_dir)
        cfg = LocalStorageConfig(type="local", base_path="${YWEB_LOCAL_PATH}")
        assert os.path.isabs(cfg.base_path)

        # 已存在但不可写
        monkeypatch.setattr("yweb.storage.config.os.path.exists", lambda p: True)
        monkeypatch.setattr("yweb.storage.config.os.access", lambda p, mode: False)
        with pytest.raises(ValueError):
            LocalStorageConfig(type="local", base_path=temp_dir)

        # 不存在且 create_dirs=False
        monkeypatch.setattr("yweb.storage.config.os.path.exists", lambda p: False)
        monkeypatch.setattr("yweb.storage.config.os.access", lambda p, mode: True)
        with pytest.raises(ValueError):
            LocalStorageConfig(type="local", base_path=temp_dir, create_dirs=False)

    def test_oss_s3_secure_url_validators(self, monkeypatch):
        monkeypatch.setenv("OSS_AK", "ak")
        monkeypatch.setenv("OSS_SK", "sk")
        monkeypatch.setenv("S3_AK", "s3-ak")
        monkeypatch.setenv("S3_SK", "s3-sk")
        monkeypatch.setenv("SECURE_K", "k" * 40)

        oss_cfg = OSSStorageConfig(
            type="oss",
            access_key_id="${OSS_AK}",
            access_key_secret="${OSS_SK}",
            endpoint="oss-cn-hz.aliyuncs.com",
            bucket_name="bucket-x",
        )
        assert oss_cfg.access_key_id == "ak"
        assert oss_cfg.access_key_secret == "sk"

        with pytest.raises(ValueError):
            OSSStorageConfig(
                type="oss",
                access_key_id="a",
                access_key_secret="b",
                endpoint="",
                bucket_name="bucket-y",
            )

        s3_cfg = S3StorageConfig(
            type="s3",
            access_key_id="${S3_AK}",
            secret_access_key="${S3_SK}",
            bucket_name="bucket-z",
        )
        assert s3_cfg.access_key_id == "s3-ak"
        assert s3_cfg.secret_access_key == "s3-sk"

        secure_cfg = SecureURLConfig(secret_key="${SECURE_K}", token_store="memory")
        assert secure_cfg.secret_key == "k" * 40
        with pytest.raises(ValueError):
            SecureURLConfig(secret_key="k" * 40, token_store="redis", redis_url=None)

    def test_storage_config_backend_validation_and_default_and_dump(self):
        # 后端配置不是 dict
        with pytest.raises(ValueError):
            StorageConfig(backends={"bad": "not-dict"})

        # 缺少 type
        with pytest.raises(ValueError):
            StorageConfig(backends={"bad": {"max_size": 1}})

        # 未知类型
        with pytest.raises(ValueError):
            StorageConfig(backends={"bad": {"type": "unknown"}})

        # 子配置错误（max_size<=0）
        with pytest.raises(ValueError):
            StorageConfig(backends={"mem": {"type": "memory", "max_size": 0}})

        # 自动 default + to_manager_config
        cfg = StorageConfig(
            backends={
                "mem": {"type": "memory", "max_size": 1024, "max_files": 10},
                "s3": {
                    "type": "s3",
                    "access_key_id": "a",
                    "secret_access_key": "b",
                    "bucket_name": "bb",
                },
            }
        )
        assert cfg.default == "mem"
        payload = cfg.to_manager_config()
        assert payload["default"] == "mem"
        assert payload["backends"]["mem"]["type"] == "memory"

        # default 指向不存在
        with pytest.raises(ValueError):
            StorageConfig(backends={"mem": {"type": "memory"}}, default="missing")

    def test_validate_config_entry(self):
        cfg = validate_config({"backends": {"mem": {"type": "memory"}}})
        assert isinstance(cfg, StorageConfig)
        assert cfg.default == "mem"
