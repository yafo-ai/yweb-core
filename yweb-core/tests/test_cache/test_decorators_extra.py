"""cache.decorators 补充测试"""

from dataclasses import dataclass

import pytest

from yweb.cache.decorators import (
    _build_value_preview,
    _is_sensitive_field,
    cache_registry,
    cached,
)


@dataclass
class PreviewObj:
    username: str
    password: str
    nested: dict


class FakeRedis:
    """最小 Redis 桩"""

    def __init__(self):
        self.store = {}

    def get(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        return self.store.get(key)

    def setex(self, key, ttl, data):
        _ = ttl
        self.store[key] = data

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
        return count

    def scan(self, cursor, match=None, count=100):
        _ = (count,)
        keys = []
        for k in list(self.store.keys()):
            text = k.decode() if isinstance(k, bytes) else str(k)
            if match is None or text.startswith(match.rstrip("*")):
                keys.append(k.encode() if isinstance(k, str) else k)
        return 0, keys

    def ttl(self, _key):
        return 30


class FakeBadRedis(FakeRedis):
    def get(self, key):
        raise RuntimeError("redis get error")


class TestDecoratorsExtra:
    """decorators 额外分支"""

    def test_sensitive_detection_and_value_preview(self):
        assert _is_sensitive_field("password_hash") is True
        assert _is_sensitive_field("display_name") is False

        preview = _build_value_preview(
            {
                "username": "alice",
                "password": "secret",
                "list_data": list(range(30)),
                "long_text": "x" * 150,
            }
        )
        assert preview["password"] == "***"
        assert preview["list_data"][-1] == "<truncated>"
        assert preview["long_text"].endswith("...")

        obj_preview = _build_value_preview(
            PreviewObj(username="alice", password="pwd", nested={"token": "abc", "x": 1})
        )
        assert obj_preview["fields"]["password"] == "***"
        assert obj_preview["fields"]["nested"]["token"] == "***"

    def test_registry_manage_and_inspect(self):
        original = dict(cache_registry._functions)
        cache_registry._functions.clear()
        try:
            @cached(ttl=60, key_prefix="reg:demo")
            def get_item(item_id: int):
                return {"id": item_id, "token": "secret-token"}

            get_item(1)
            get_item(2)
            listed = cache_registry.list_functions()
            assert len(listed) == 1
            assert listed[0]["name"] == "get_item"

            all_stats = cache_registry.get_all_stats()
            assert all_stats["total_functions"] == 1

            entries = cache_registry.list_entries("get_item", limit=10)
            assert entries["total"] >= 1
            first_key = entries["entries"][0]["key"]
            single = cache_registry.get_entry("get_item", first_key)
            assert single is not None
            assert single["value_preview"]["token"] == "***"

            assert cache_registry.clear_function("get_item") is True
            assert cache_registry.clear_function("no_such") is False
            assert cache_registry.unregister("get_item") is True
            assert cache_registry.unregister("get_item") is False
            assert cache_registry.get("get_item") is None
            assert cache_registry.clear_all() == 0
        finally:
            cache_registry._functions.clear()
            cache_registry._functions.update(original)

    def test_cached_redis_backend_and_invalid_inputs(self):
        with pytest.raises(ValueError):
            @cached(ttl=30, backend="redis", redis=None)
            def bad(_x):
                return _x

        redis = FakeRedis()
        call_count = 0

        @cached(ttl=30, backend="redis", redis=redis, key_prefix="r:demo")
        def get_user(uid: int):
            nonlocal call_count
            call_count += 1
            return {"id": uid}

        assert get_user(1)["id"] == 1
        assert get_user(1)["id"] == 1  # hit
        assert call_count == 1
        assert get_user.inspect_entries(limit=5) != []
        key = get_user.inspect_entries(limit=1)[0]["key"]
        assert get_user.inspect_entry(key)["ttl_remaining"] == 30

    def test_redis_inspect_error_branches(self):
        redis = FakeBadRedis()

        @cached(ttl=30, backend="redis", redis=redis, key_prefix="r:bad")
        def f(uid: int):
            return {"id": uid}

        # get 出错 -> miss
        assert f(1)["id"] == 1

        # inspect_entry / inspect_entries 异常路径
        assert f.inspect_entry("any") is None
        assert f.inspect_entries(limit=10) == []
