"""OSSStorage 额外分支覆盖测试（新文件）"""

from io import BytesIO
from types import SimpleNamespace
import importlib
import sys

import pytest

from yweb.storage.exceptions import StorageError


class NoSuchKeyError(Exception):
    pass


class FakeObject:
    def __init__(self, key, size=1, last_modified=None, etag='"etag"', is_prefix=False):
        self.key = key
        self.size = size
        self.last_modified = last_modified
        self.etag = etag
        self._prefix = is_prefix

    def is_prefix(self):
        return self._prefix


class FakeBucket:
    def __init__(self):
        self.raise_put = None
        self.raise_get = None
        self.raise_delete = None
        self.raise_head = None
        self.raise_copy = None
        self.raise_bucket_info = None
        self.exists_value = False
        self.put_calls = []

    def put_object(self, key, content, headers=None):
        if self.raise_put:
            raise self.raise_put
        self.put_calls.append((key, content, headers))

    def get_object(self, key):
        if self.raise_get:
            raise self.raise_get
        return SimpleNamespace(read=lambda: b"content")

    def delete_object(self, key):
        if self.raise_delete:
            raise self.raise_delete
        return True

    def object_exists(self, key):
        return self.exists_value

    def head_object(self, key):
        if self.raise_head:
            raise self.raise_head
        return SimpleNamespace(
            content_length=3,
            content_type="text/plain",
            etag='"abc"',
            headers={
                "Last-Modified": "bad-date",
                "x-oss-meta-k1": "v1",
                "X-OSS-META-K2": "v2",
            },
        )

    def sign_url(self, method, key, expires, params=None, headers=None):
        _ = (method, key, expires, params, headers)
        return "signed-url"

    def copy_object(self, bucket_name, src_key, dst_key):
        _ = (bucket_name, src_key, dst_key)
        if self.raise_copy:
            raise self.raise_copy
        return True

    def get_bucket_info(self):
        if self.raise_bucket_info:
            raise self.raise_bucket_info
        return SimpleNamespace(
            name="b",
            location="cn-hz",
            creation_date="2024-01-01",
            storage_class="Standard",
        )


class TestOSSExtraMore:
    def _load_oss_module(self, monkeypatch, with_fake_oss2=False):
        if with_fake_oss2:
            fake_oss2 = SimpleNamespace(
                exceptions=SimpleNamespace(NoSuchKey=NoSuchKeyError),
                Auth=lambda ak, sk: ("auth", ak, sk),
                Bucket=lambda auth, endpoint, bucket_name, connect_timeout=30: FakeBucket(),
                ObjectIterator=lambda *args, **kwargs: [],
            )
            monkeypatch.setitem(sys.modules, "oss2", fake_oss2)
        else:
            monkeypatch.delitem(sys.modules, "oss2", raising=False)
        import yweb.storage.backends.oss as oss_mod
        return importlib.reload(oss_mod)

    def _make_storage(self, prefix="uploads"):
        oss_mod = importlib.import_module("yweb.storage.backends.oss")
        s = oss_mod.OSSStorage.__new__(oss_mod.OSSStorage)
        s.prefix = prefix
        s.endpoint = "oss-cn-hz.aliyuncs.com"
        s.bucket_name = "bucket"
        s.bucket = FakeBucket()
        s.internal_bucket = None
        return s

    def test_init_import_error_and_internal_bucket(self, monkeypatch):
        oss_mod = self._load_oss_module(monkeypatch, with_fake_oss2=False)
        with pytest.raises(ImportError):
            oss_mod.OSSStorage("ak", "sk", "ep", "b")

        # 覆盖 __init__ 内 internal_bucket 分支
        oss_mod = self._load_oss_module(monkeypatch, with_fake_oss2=True)
        fake_oss2 = SimpleNamespace()
        fake_oss2.Auth = lambda ak, sk: ("auth", ak, sk)
        bucket_calls = []

        def _bucket(auth, endpoint, bucket_name, connect_timeout=30):
            bucket_calls.append((auth, endpoint, bucket_name, connect_timeout))
            return FakeBucket()

        fake_oss2.Bucket = _bucket
        fake_oss2.exceptions = SimpleNamespace(NoSuchKey=NoSuchKeyError)
        monkeypatch.setattr(oss_mod, "HAS_OSS2", True)
        monkeypatch.setattr(oss_mod, "oss2", fake_oss2)

        s = oss_mod.OSSStorage("ak", "sk", "external", "bucket", internal_endpoint="internal")
        assert s.internal_bucket is not None
        assert len(bucket_calls) == 2

    def test_save_fileobj_and_errors(self, monkeypatch):
        self._load_oss_module(monkeypatch, with_fake_oss2=True)
        s = self._make_storage()
        s.bucket.exists_value = False
        s.save("a.txt", BytesIO(b"x"), metadata={"a": 1})
        assert s.bucket.put_calls
        assert "x-oss-meta-a" in (s.bucket.put_calls[0][2] or {})

        s.bucket.raise_put = RuntimeError("put fail")
        with pytest.raises(StorageError):
            s.save("a.txt", b"x")

    def test_read_and_read_bytes_error_branches(self, monkeypatch):
        oss_mod = self._load_oss_module(monkeypatch, with_fake_oss2=True)
        s = self._make_storage()
        fake_oss2 = SimpleNamespace(exceptions=SimpleNamespace(NoSuchKey=NoSuchKeyError))
        monkeypatch.setattr(oss_mod, "oss2", fake_oss2)

        s.bucket.raise_get = NoSuchKeyError("x")
        with pytest.raises(FileNotFoundError):
            s.read("x.txt")
        with pytest.raises(FileNotFoundError):
            s.read_bytes("x.txt")

        s.bucket.raise_get = RuntimeError("NoSuchKey xx")
        with pytest.raises(FileNotFoundError):
            s.read("x.txt")
        with pytest.raises(FileNotFoundError):
            s.read_bytes("x.txt")

        s.bucket.raise_get = RuntimeError("network")
        with pytest.raises(StorageError):
            s.read("x.txt")
        with pytest.raises(StorageError):
            s.read_bytes("x.txt")

    def test_delete_get_info_list_and_urls(self, monkeypatch):
        oss_mod = self._load_oss_module(monkeypatch, with_fake_oss2=True)
        s = self._make_storage()
        fake_oss2 = SimpleNamespace(exceptions=SimpleNamespace(NoSuchKey=NoSuchKeyError))
        monkeypatch.setattr(oss_mod, "oss2", fake_oss2)

        s.bucket.raise_delete = RuntimeError("del fail")
        assert s.delete("a.txt") is False

        s.bucket.raise_head = NoSuchKeyError("missing")
        with pytest.raises(FileNotFoundError):
            s.get_info("x")

        s.bucket.raise_head = RuntimeError("NoSuchKey in msg")
        with pytest.raises(FileNotFoundError):
            s.get_info("x")

        s.bucket.raise_head = RuntimeError("other")
        with pytest.raises(StorageError):
            s.get_info("x")

        s.bucket.raise_head = None
        info = s.get_info("a/b.txt")
        assert info.path == "a/b.txt"
        assert info.etag == "abc"
        assert info.metadata["k1"] == "v1"
        assert info.metadata["k2"] == "v2"
        assert info.modified_at is None

        # list 分支：prefix、非递归、limit、跳过目录对象
        objs = [
            FakeObject("uploads/p/", is_prefix=True),
            FakeObject("uploads/p/a.txt", size=10, last_modified=1700000000, etag='"e1"'),
            FakeObject("uploads/p/b.txt", size=20, last_modified="bad", etag=None),
        ]
        monkeypatch.setattr(oss_mod.oss2, "ObjectIterator", lambda *a, **k: objs, raising=False)
        listed = s.list(prefix="p", recursive=False, limit=1)
        assert len(listed) == 1
        assert listed[0].path == "p/a.txt"

        # 下载URL分支（filename 编码 + internal_bucket）
        s.internal_bucket = FakeBucket()
        url = s.get_url("p/a.txt", download=True, filename="中文.txt", internal=True)
        assert url == "signed-url"
        up = s.get_upload_url("p/new.txt", content_type="text/plain")
        assert up == "signed-url"

    def test_copy_bucket_info_and_path_helpers(self, monkeypatch):
        oss_mod = self._load_oss_module(monkeypatch, with_fake_oss2=True)
        s = self._make_storage(prefix="")
        fake_oss2 = SimpleNamespace(exceptions=SimpleNamespace(NoSuchKey=NoSuchKeyError))
        monkeypatch.setattr(oss_mod, "oss2", fake_oss2)

        s.bucket.exists_value = True
        with pytest.raises(FileExistsError):
            s.copy("a.txt", "b.txt", overwrite=False)

        s.bucket.exists_value = False
        s.bucket.raise_copy = NoSuchKeyError("src missing")
        with pytest.raises(FileNotFoundError):
            s.copy("a.txt", "b.txt")

        s.bucket.raise_copy = RuntimeError("copy fail")
        with pytest.raises(StorageError):
            s.copy("a.txt", "b.txt")

        s.bucket.raise_copy = None
        assert s.copy("a.txt", "b.txt") == "b.txt"

        assert s.get_bucket_info()["name"] == "b"
        s.bucket.raise_bucket_info = RuntimeError("nope")
        with pytest.raises(StorageError):
            s.get_bucket_info()

        assert s._full_key("/x.txt") == "x.txt"
        assert s._strip_prefix("abc/x.txt") == "abc/x.txt"
        s2 = self._make_storage(prefix="pre")
        assert s2._full_key("x.txt") == "pre/x.txt"
        assert s2._strip_prefix("pre/x.txt") == "x.txt"
        assert s2._strip_prefix("other/x.txt") == "other/x.txt"
