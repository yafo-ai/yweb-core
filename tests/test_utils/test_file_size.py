"""文件大小工具测试

测试文件大小解析、格式化和验证功能
"""

import pytest

from yweb.utils import (
    parse_file_size,
    format_file_size,
    validate_file_size,
)


class TestParseFileSize:
    """parse_file_size 函数测试"""
    
    def test_parse_bytes(self):
        """测试解析字节"""
        assert parse_file_size("100B") == 100
        assert parse_file_size("100 B") == 100
        assert parse_file_size("100b") == 100
    
    def test_parse_kilobytes(self):
        """测试解析千字节"""
        assert parse_file_size("1KB") == 1024
        assert parse_file_size("1 KB") == 1024
        assert parse_file_size("1kb") == 1024
        assert parse_file_size("10KB") == 10 * 1024
    
    def test_parse_megabytes(self):
        """测试解析兆字节"""
        assert parse_file_size("1MB") == 1024 * 1024
        assert parse_file_size("10MB") == 10 * 1024 * 1024
        assert parse_file_size("100 MB") == 100 * 1024 * 1024
    
    def test_parse_gigabytes(self):
        """测试解析千兆字节"""
        assert parse_file_size("1GB") == 1024 * 1024 * 1024
        assert parse_file_size("2 GB") == 2 * 1024 * 1024 * 1024
    
    def test_parse_terabytes(self):
        """测试解析太字节"""
        assert parse_file_size("1TB") == 1024 ** 4
        assert parse_file_size("2TB") == 2 * (1024 ** 4)
    
    def test_parse_decimal_values(self):
        """测试解析小数值"""
        assert parse_file_size("1.5MB") == int(1.5 * 1024 * 1024)
        assert parse_file_size("0.5GB") == int(0.5 * 1024 * 1024 * 1024)
        assert parse_file_size("2.5KB") == int(2.5 * 1024)
    
    def test_parse_without_unit(self):
        """测试解析无单位（纯数字）"""
        assert parse_file_size("1000") == 1000
        assert parse_file_size("512") == 512
    
    def test_parse_case_insensitive(self):
        """测试大小写不敏感"""
        assert parse_file_size("10mb") == parse_file_size("10MB")
        assert parse_file_size("10Mb") == parse_file_size("10MB")
        assert parse_file_size("10mB") == parse_file_size("10MB")
    
    def test_parse_with_extra_spaces(self):
        """测试带额外空格"""
        assert parse_file_size("  10  MB  ") == 10 * 1024 * 1024
        assert parse_file_size("5 KB") == 5 * 1024
    
    def test_parse_zero(self):
        """测试解析零"""
        assert parse_file_size("0B") == 0
        assert parse_file_size("0MB") == 0
        assert parse_file_size("0") == 0
    
    def test_parse_invalid_format(self):
        """测试无效格式抛出异常"""
        with pytest.raises(ValueError):
            parse_file_size("invalid")
        
        with pytest.raises(ValueError):
            parse_file_size("MB10")
        
        with pytest.raises(ValueError):
            parse_file_size("10XX")
    
    def test_parse_negative_value(self):
        """测试负值"""
        assert parse_file_size("-10MB") == -10 * 1024 * 1024


class TestFormatFileSize:
    """format_file_size 函数测试"""
    
    def test_format_bytes(self):
        """测试格式化字节"""
        assert format_file_size(100) == "100.00 B"
        assert format_file_size(512) == "512.00 B"
        assert format_file_size(1) == "1.00 B"
    
    def test_format_kilobytes(self):
        """测试格式化千字节"""
        assert format_file_size(1024) == "1.00 KB"
        assert format_file_size(1536) == "1.50 KB"
        assert format_file_size(10240) == "10.00 KB"
    
    def test_format_megabytes(self):
        """测试格式化兆字节"""
        assert format_file_size(1024 * 1024) == "1.00 MB"
        assert format_file_size(5 * 1024 * 1024) == "5.00 MB"
    
    def test_format_gigabytes(self):
        """测试格式化千兆字节"""
        assert format_file_size(1024 * 1024 * 1024) == "1.00 GB"
        assert format_file_size(2 * 1024 * 1024 * 1024) == "2.00 GB"
    
    def test_format_terabytes(self):
        """测试格式化太字节"""
        assert format_file_size(1024 ** 4) == "1.00 TB"
    
    def test_format_zero(self):
        """测试格式化零"""
        assert format_file_size(0) == "0.00 B"
    
    def test_format_custom_decimal_places(self):
        """测试自定义小数位数"""
        size = 1536  # 1.5 KB
        assert format_file_size(size, precision=0) == "2 KB"
        assert format_file_size(size, precision=1) == "1.5 KB"
        assert format_file_size(size, precision=3) == "1.500 KB"

    def test_format_decimal_base(self):
        """测试十进制单位格式化"""
        assert format_file_size(1000, precision=0, binary=False) == "1 KB"
        assert format_file_size(1500, precision=1, binary=False) == "1.5 KB"
    
    def test_format_large_file(self):
        """测试格式化大文件"""
        size = 1.5 * (1024 ** 4)  # 1.5 TB
        result = format_file_size(int(size))
        assert "TB" in result
    
    def test_format_round_trip(self):
        """测试格式化和解析往返"""
        original_sizes = [100, 1024, 10240, 1048576, 1073741824]
        
        for original in original_sizes:
            formatted = format_file_size(original)
            # 从格式化结果中提取数值部分
            parsed = parse_file_size(formatted)
            # 由于舍入，可能不完全相等
            assert abs(parsed - original) <= 1


class TestValidateFileSize:
    """validate_file_size 函数测试"""
    
    def test_validate_within_range(self):
        """测试在范围内的文件大小"""
        assert validate_file_size("5MB", min_size="1MB", max_size="10MB") == True
        assert validate_file_size("100KB", min_size="50KB", max_size="200KB") == True
    
    def test_validate_exact_min(self):
        """测试等于最小值"""
        assert validate_file_size("1MB", min_size="1MB", max_size="10MB") == True
    
    def test_validate_exact_max(self):
        """测试等于最大值"""
        assert validate_file_size("10MB", min_size="1MB", max_size="10MB") == True
    
    def test_validate_below_min(self):
        """测试低于最小值"""
        assert validate_file_size("500KB", min_size="1MB", max_size="10MB") == False
    
    def test_validate_above_max(self):
        """测试超过最大值"""
        assert validate_file_size("15MB", min_size="1MB", max_size="10MB") == False
    
    def test_validate_no_min(self):
        """测试无最小值限制"""
        assert validate_file_size("100B", max_size="10MB") == True
        assert validate_file_size("15MB", max_size="10MB") == False
    
    def test_validate_no_max(self):
        """测试无最大值限制"""
        assert validate_file_size("100MB", min_size="1MB") == True
        assert validate_file_size("500KB", min_size="1MB") == False
    
    def test_validate_no_limits(self):
        """测试无限制"""
        assert validate_file_size("1KB") == True
        assert validate_file_size("1TB") == True
    
    def test_validate_invalid_format(self):
        """测试无效格式"""
        assert validate_file_size("invalid") == False
        assert validate_file_size("", min_size="1MB") == False
    
    def test_validate_different_units(self):
        """测试不同单位比较"""
        assert validate_file_size("2048KB", min_size="1MB", max_size="3MB") == True
        assert validate_file_size("1GB", min_size="500MB", max_size="2GB") == True


class TestFileSizeEdgeCases:
    """文件大小边界情况测试"""
    
    def test_very_small_files(self):
        """测试非常小的文件"""
        assert parse_file_size("1B") == 1
        assert format_file_size(1) == "1.00 B"
    
    def test_very_large_files(self):
        """测试非常大的文件"""
        # 1 PB = 1024 TB
        pb_bytes = 1024 ** 5
        assert format_file_size(pb_bytes) == "1.00 PB"
    
    def test_floating_point_precision(self):
        """测试浮点精度"""
        # 1.1 MB
        size = int(1.1 * 1024 * 1024)
        formatted = format_file_size(size)
        
        # 验证结果合理
        assert "MB" in formatted or "KB" in formatted
    
    def test_boundary_values(self):
        """测试边界值"""
        # 刚好 1 KB
        assert parse_file_size("1024B") == 1024
        
        # 刚好 1 MB
        assert parse_file_size("1024KB") == 1024 * 1024
        
        # 刚好 1 GB
        assert parse_file_size("1024MB") == 1024 * 1024 * 1024

