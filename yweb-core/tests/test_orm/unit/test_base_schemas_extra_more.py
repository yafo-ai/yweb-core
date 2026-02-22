"""base_schemas 额外分支测试（新文件）"""

from datetime import datetime

import pytest
from pydantic import BaseModel

from yweb.orm.base_schemas import (
    DateTimeStr,
    Page,
    PaginationField,
    PaginationTmpField,
    format_datetime_to_string,
)


class DateHolder(BaseModel):
    value: DateTimeStr = None


class TestBaseSchemasExtraMore:
    def test_format_datetime_to_string(self):
        assert format_datetime_to_string(None) is None
        assert format_datetime_to_string(datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02 03:04:05"
        assert format_datetime_to_string(123) == "123"

    def test_datetime_str_and_page_iter(self):
        m = DateHolder(value=datetime(2024, 9, 1, 8, 7, 6))
        assert m.value == "2024-09-01 08:07:06"

        page = Page(rows=[1, 2], total_records=5, page=1, page_size=2, total_pages=3)
        assert page.has_next is True
        assert page.has_prev is False
        data = page.to_dict()
        assert data["has_next"] is True
        pairs = dict(iter(page))
        assert pairs["has_next"] is True
        assert pairs["has_prev"] is False

    def test_pagination_validators(self):
        p = PaginationField(page=0, page_size=0)
        assert p.page == 1
        assert p.page_size == 1

        p2 = PaginationTmpField(page_index=0, page_size=0)
        assert p2.page_index == 1
        assert p2.page_size == 1

        with pytest.raises(TypeError):
            PaginationTmpField(page_index=None, page_size=None)
