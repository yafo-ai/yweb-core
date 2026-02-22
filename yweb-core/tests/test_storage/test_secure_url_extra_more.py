"""secure_url 额外分支覆盖测试（新文件）"""

from datetime import datetime, timedelta

from yweb.storage.secure_url import (
    RedisTokenStore,
    SecureURLGenerator,
    TokenInfo,
    TokenStore,
)


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttl_map = {}
        self.eval_result = 1
        self.raise_eval = False

    def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttl_map[key] = ttl

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1

    def ttl(self, key):
        return self.ttl_map.get(key, -1)

    def eval(self, script, keys_count, key):
        _ = (script, keys_count, key)
        if self.raise_eval:
            raise RuntimeError("eval down")
        return self.eval_result


class MemoryLikeStore:
    """用于触发 validate_token 的二次过期检查路径"""

    def __init__(self, info):
        self.info = info
        self.deleted = []

    def set(self, token, info, ttl):
        _ = (token, info, ttl)

    def get(self, token):
        _ = token
        return self.info

    def delete(self, token):
        self.deleted.append(token)

    def increment_downloads(self, token):
        _ = token
        return 1


class TestSecureURLExtraMore:
    def test_token_store_abstract_methods_raise(self):
        store = TokenStore()
        info = TokenInfo(file_path="a", expires_at=datetime.now() + timedelta(seconds=60))

        for fn, args in [
            (store.set, ("t", info, 10)),
            (store.get, ("t",)),
            (store.delete, ("t",)),
            (store.increment_downloads, ("t",)),
        ]:
            try:
                fn(*args)
                assert False, "should raise"
            except NotImplementedError:
                pass

    def test_redis_store_set_get_delete_and_get_parse_error(self):
        redis = FakeRedis()
        store = RedisTokenStore(redis, prefix="p:")
        info = TokenInfo(file_path="x/a.txt", expires_at=datetime.now() + timedelta(hours=1))

        store.set("abc", info, ttl=120)
        loaded = store.get("abc")
        assert loaded is not None
        assert loaded.file_path == "x/a.txt"

        # 非法 JSON 命中 249-251
        redis.data["p:bad"] = "{not-json"
        assert store.get("bad") is None

        store.delete("abc")
        assert store.get("abc") is None

    def test_redis_increment_downloads_eval_success_and_negative(self):
        redis = FakeRedis()
        store = RedisTokenStore(redis)
        info = TokenInfo(file_path="f.txt", expires_at=datetime.now() + timedelta(minutes=5))
        store.set("k1", info, ttl=300)

        redis.eval_result = 3
        assert store.increment_downloads("k1") == 3

        # eval 返回负数命中 272
        redis.eval_result = -1
        assert store.increment_downloads("k1") == 0

    def test_redis_increment_downloads_fallback_with_ttl_and_without(self):
        redis = FakeRedis()
        store = RedisTokenStore(redis)
        info = TokenInfo(
            file_path="f2.txt",
            expires_at=datetime.now() + timedelta(minutes=5),
            download_count=4,
        )
        store.set("k2", info, ttl=180)

        # eval 异常 -> 走降级路径，ttl>0 会 set
        redis.raise_eval = True
        assert store.increment_downloads("k2") == 5
        assert redis.ttl("storage:token:k2") > 0

        # token 不存在 -> 0
        assert store.increment_downloads("missing") == 0

        # ttl<=0 分支（不 set）
        redis.data["storage:token:k3"] = (
            '{"file_path":"f3","expires_at":"2099-01-01T00:00:00",'
            '"download_count":1,"metadata":{}}'
        )
        redis.ttl_map["storage:token:k3"] = -1
        assert store.increment_downloads("k3") == 2

    def test_generator_short_secret_and_expired_double_check(self):
        gen = SecureURLGenerator(secret_key="short-key", base_url="/f")
        token = gen.generate("a.txt").token
        assert token

        expired_info = TokenInfo(
            file_path="x",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        store = MemoryLikeStore(expired_info)
        gen2 = SecureURLGenerator(secret_key="long-secret-key-xxxxxxxx", token_store=store)
        assert gen2.validate_token("t1") is None
        assert "t1" in store.deleted

    def test_validate_signed_padding_and_decode_error(self):
        gen = SecureURLGenerator(secret_key="long-secret-key-xxxxxxxx")

        # 编码长度可被 4 整除，命中 508
        file_path = gen.validate_signed(
            encoded_path="YWJjZA==",
            expires=int((datetime.now() + timedelta(minutes=3)).timestamp()),
            signature="bad-sign",
        )
        assert file_path is None

        # Base64 解码失败命中 512-514
        file_path2 = gen.validate_signed(
            encoded_path="!!!not-base64!!!",
            expires=int((datetime.now() + timedelta(minutes=3)).timestamp()),
            signature="whatever",
        )
        assert file_path2 is None
