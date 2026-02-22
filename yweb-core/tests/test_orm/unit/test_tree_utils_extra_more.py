"""tree_utils 额外分支测试（新文件）"""

from yweb.orm.tree.tree_utils import (
    build_tree_list,
    calculate_tree_depth,
    filter_tree,
    find_node_in_tree,
    flatten_tree,
    get_node_path,
    validate_no_circular_reference,
)


class TestTreeUtilsExtraMore:
    def test_build_tree_custom_root_and_sort(self):
        assert build_tree_list([]) == []
        rows = [
            {"id": 2, "pid": 0, "name": "B", "order": 2},
            {"id": 1, "pid": 0, "name": "A", "order": 1},
            {"id": 3, "pid": 1, "name": "A-1", "order": 1},
            {"id": 9, "pid": 999, "name": "orphan", "order": 1},
        ]
        tree = build_tree_list(
            rows,
            id_field="id",
            parent_field="pid",
            children_field="kids",
            root_parent_value=0,
            sort_key=lambda n: n["order"],
        )
        assert [n["id"] for n in tree] == [1, 2]
        assert tree[0]["kids"][0]["id"] == 3

    def test_flatten_find_path_and_depth(self):
        tree = [
            {"id": 1, "name": "R", "children": [{"id": 2, "name": "C", "children": []}]},
        ]
        flat = flatten_tree(tree, include_children_field=True, level_field="lvl")
        assert flat[0]["lvl"] == 1
        assert flat[1]["lvl"] == 2
        assert "children" in flat[0]

        assert find_node_in_tree(tree, target_id=2)["name"] == "C"
        assert find_node_in_tree(tree, target_id=999) is None

        path = get_node_path(tree, target_id=2)
        assert [n["id"] for n in path] == [1, 2]
        assert get_node_path(tree, target_id=999) == []

        assert calculate_tree_depth(tree) == 2
        assert calculate_tree_depth([]) == 0

    def test_validate_no_circular_and_filter_keep_ancestors(self):
        assert validate_no_circular_reference(1, None, lambda pid: []) is True
        assert validate_no_circular_reference(1, 1, lambda pid: []) is False
        assert validate_no_circular_reference(1, 9, lambda pid: [3, 4]) is True
        assert validate_no_circular_reference(1, 9, lambda pid: [1, 4]) is False

        tree = [
            {
                "id": 1,
                "ok": False,
                "children": [
                    {"id": 2, "ok": False, "children": []},
                    {"id": 3, "ok": True, "children": []},
                ],
            }
        ]
        kept = filter_tree(tree, lambda n: n.get("ok", False), keep_ancestors=True)
        assert len(kept) == 1
        assert kept[0]["children"][0]["id"] == 3

        strict = filter_tree(tree, lambda n: n.get("ok", False), keep_ancestors=False)
        assert strict == []
