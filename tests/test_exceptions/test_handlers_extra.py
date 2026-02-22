"""exceptions.handlers 补充测试"""

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from yweb.exceptions.exceptions import BusinessException
from yweb.exceptions.handlers import (
    ValidationErrorTranslator,
    business_exception_handler,
    general_exception_handler,
    http_exception_handler,
)


def _build_request(path: str = "/x", method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    req = Request(scope)
    req.state.request_id = "rid-extra"
    return req


class TestValidationTranslatorExtra:
    def test_custom_dynamic_context_and_fallback(self):
        ValidationErrorTranslator.add_messages({"value_error.phone": "手机号格式错误"})
        assert (
            ValidationErrorTranslator.translate("value_error.phone", {"ctx": {}})
            == "手机号格式错误"
        )

        @ValidationErrorTranslator.translator("value_error.custom_range")
        def custom_range(ctx: dict) -> str:
            return f"范围: {ctx.get('min')}~{ctx.get('max')}"

        assert (
            ValidationErrorTranslator.translate(
                "value_error.custom_range",
                {"ctx": {"min": 1, "max": 9}},
            )
            == "范围: 1~9"
        )

        msg = ValidationErrorTranslator.translate(
            "string_too_short",
            {"ctx": {"min_length": 6}},
        )
        assert msg is not None

        enum_msg = ValidationErrorTranslator.translate(
            "enum",
            {"ctx": {"expected": ["a", "b"]}},
        )
        assert "a, b" in enum_msg

        ValidationErrorTranslator.configure(
            {
                "fallback_translations": {"must be positive": "必须为正数"},
            }
        )
        assert (
            ValidationErrorTranslator.fallback_translate("value must be positive")
            == "value 必须为正数"
        )


class TestHandlersExtra:
    @pytest.mark.asyncio
    async def test_business_handler_debug_info_and_without_error_code(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "true")
        request = _build_request("/biz", "POST")
        exc = BusinessException("失败", code="", details=["d1"], trace_id="t1")
        resp = await business_exception_handler(request, exc)
        body = resp.body.decode("utf-8")
        assert '"message":"失败"' in body
        assert '"debug_info"' in body
        assert '"error_code"' not in body
        monkeypatch.delenv("DEBUG", raising=False)

    @pytest.mark.asyncio
    async def test_http_handler_warning_and_error_levels(self):
        request = _build_request("/http")
        resp_404 = await http_exception_handler(
            request, StarletteHTTPException(status_code=404, detail="not found")
        )
        assert resp_404.status_code == 404
        assert "HTTP_404" in resp_404.body.decode("utf-8")

        resp_503 = await http_exception_handler(
            request, StarletteHTTPException(status_code=503, detail="down")
        )
        assert resp_503.status_code == 503
        assert "HTTP_503" in resp_503.body.decode("utf-8")

    @pytest.mark.asyncio
    async def test_general_handler_debug_and_non_debug(self, monkeypatch):
        request = _build_request("/err")

        # 非调试模式
        monkeypatch.setenv("DEBUG", "false")
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            resp = await general_exception_handler(request, exc)
        assert resp.status_code == 500
        text = resp.body.decode("utf-8")
        assert "INTERNAL_SERVER_ERROR" in text
        assert "debug_info" not in text

        # 调试模式
        monkeypatch.setenv("DEBUG", "true")
        try:
            raise ValueError("bad")
        except ValueError as exc:
            resp2 = await general_exception_handler(request, exc)
        assert resp2.status_code == 500
        text2 = resp2.body.decode("utf-8")
        assert "debug_info" in text2
        assert "ValueError" in text2

    @pytest.mark.asyncio
    async def test_validation_handler_with_untranslated_message(self):
        request = _build_request("/v")
        exc = RequestValidationError(
            [
                {
                    "type": "unknown_rule",
                    "loc": ("body", "price"),
                    "msg": "value must be positive",
                    "input": -1,
                }
            ]
        )

        from yweb.exceptions.handlers import validation_exception_handler

        resp = await validation_exception_handler(request, exc)
        assert resp.status_code == 422
        assert "price" in resp.body.decode("utf-8")
