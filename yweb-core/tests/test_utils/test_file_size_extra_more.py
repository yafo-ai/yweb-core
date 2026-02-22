"""file_size 额外分支覆盖测试（新文件）"""

from yweb.utils.file_size import format_file_size, human_readable_size, parse_file_size


class TestFileSizeExtraMore:
    def test_parse_numeric_and_alias_and_error_branches(self):
        # 数字直返（line 67）
        assert parse_file_size(12.8) == 12

        # 别名转换（77-78）
        assert parse_file_size("2K") == 2 * 1024
        assert parse_file_size("3M") == 3 * 1024 * 1024

        # 单位存在但无数字（85）
        try:
            parse_file_size("KB")
            assert False, "should fail"
        except ValueError:
            pass

        # 浮点转换失败（89-90）
        try:
            parse_file_size("abcMB")
            assert False, "should fail"
        except ValueError:
            pass

    def test_format_negative_and_huge_value(self):
        # 负值递归（123）
        assert format_file_size(-1536, precision=1) == "-1.5 KB"

        # 超大值命中循环后返回（134）
        huge = 1024 ** 8
        assert format_file_size(huge).endswith(" EB")

    def test_human_readable_size_paths(self):
        # 152-158 主分支（整数/小数）
        assert human_readable_size(2048) == "2 KB"
        assert human_readable_size(1536) == "1.5 KB"

        # 尾分支（小于1B阈值）
        assert human_readable_size(0.5) == "0.5 B"
