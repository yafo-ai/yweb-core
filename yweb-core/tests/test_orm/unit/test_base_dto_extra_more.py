"""base_dto 额外分支测试（新文件）"""

from datetime import datetime
from types import SimpleNamespace

from yweb.orm.base_dto import DTO


class DemoDTO(DTO):
    id: int | None = None
    name: str | None = None
    created_at: str | None = None
    is_active: str | None = None
    tags: list[dict] = []
    parent_id: int | None = None

    _field_mapping = {"is_active": "status"}
    _value_processors = {
        "is_active": lambda v: "active" if v else "inactive",
        "tags": lambda v: [{"name": x} for x in (v or [])],
    }


class TestBaseDTOExtraMore:
    def test_format_safe_and_process_value_helpers(self):
        assert DemoDTO._format_datetime(None) is None
        assert DemoDTO._format_datetime(datetime(2025, 1, 2, 3, 4, 5)) == "2025-01-02 03:04:05"
        assert DemoDTO._format_datetime(123) == "123"

        class EmptyObj:
            pass

        assert DemoDTO._safe_value(None) is None
        assert DemoDTO._safe_value({}) is None
        assert DemoDTO._safe_value(EmptyObj()) is None
        assert DemoDTO._safe_value({"k": 1}) == {"k": 1}

        assert DemoDTO._process_value(datetime(2024, 2, 3, 4, 5, 6)) == "2024-02-03 04:05:06"

    def test_from_entity_from_list_from_page(self):
        entity = SimpleNamespace(
            id=1,
            name="tom",
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            is_active=True,
            tags=["r1", "r2"],
        )
        dto = DemoDTO.from_entity(entity)
        assert dto.is_active == "active"
        assert dto.tags == [{"name": "r1"}, {"name": "r2"}]
        assert dto.created_at == "2024-01-01 00:00:00"

        assert DemoDTO.from_list(None) == []
        dto_list = DemoDTO.from_list([entity])
        assert len(dto_list) == 1

        # rows 分支
        page_rows = SimpleNamespace(
            rows=[entity],
            total_records=11,
            page=2,
            page_size=5,
            total_pages=3,
            has_prev=True,
            has_next=True,
        )
        data_rows = DemoDTO.from_page(page_rows)
        assert data_rows["total_records"] == 11
        assert data_rows["rows"][0].name == "tom"

        # items + total/per_page/pages 兼容分支
        page_items = SimpleNamespace(items=[entity], total=9, per_page=4, pages=3)
        data_items = DemoDTO.from_page(page_items)
        assert data_items["total_records"] == 9
        assert data_items["page_size"] == 4
        assert data_items["total_pages"] == 3

    def test_from_dict_tree_and_mapping_methods(self):
        dto = DemoDTO.from_dict(
            {
                "id": 10,
                "name": "alice",
                "created_at": datetime(2024, 6, 1, 12, 0, 0),
                "is_active": False,
                "tags": ["x"],
                "unknown": "ignored",
            }
        )
        assert dto.created_at == "2024-06-01 12:00:00"
        assert dto.is_active == "inactive"
        assert dto.tags == [{"name": "x"}]

        dto2 = DemoDTO.from_dict(None)
        assert dto2.id is None

        root = SimpleNamespace(id=1, name="root", parent_id=None)
        child = SimpleNamespace(id=2, name="child", parent_id=1)
        tree = DemoDTO.from_tree([root, child], parent_id=None)
        assert len(tree) == 1
        assert tree[0]["children"][0]["id"] == 2
        assert DemoDTO.from_tree(None) == []

        dumped = dto.model_dump()
        assert "status" in dumped and "is_active" not in dumped

        as_dict = dict(dto)
        assert "status" in as_dict
        assert dto["status"] == as_dict["status"]
        assert "status" in dto.keys()
        assert as_dict["status"] in dto.values()
        assert ("status", as_dict["status"]) in dto.items()
        assert dto.to_dict()["status"] == as_dict["status"]
