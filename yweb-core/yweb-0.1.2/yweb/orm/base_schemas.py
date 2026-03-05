from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TypeVar, Generic, List, Any

from pydantic import BaseModel as PydanticBaseModel, Field, model_validator, PlainSerializer, BeforeValidator
from typing_extensions import Annotated


def format_datetime_to_string(value: Any) -> Optional[str]:
    """
    将 datetime 对象格式化为字符串
    
    如果输入值为 None，返回 None
    如果输入值是 datetime 对象，将其格式化为 "YYYY-MM-DD HH:MM:SS" 格式的字符串
    其他情况返回值的字符串表示
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


DateTimeStr = Annotated[
    Optional[str],
    BeforeValidator(format_datetime_to_string),
    PlainSerializer(lambda x: x, return_type=str)
]

T = TypeVar("T")


# 统一分页响应


@dataclass
class Page(Generic[T]):
    rows: List[T]  # 当前页数据
    total_records: int  # 总条数
    page: int  # 当前页码
    page_size: int  # 每页条数
    total_pages: int  # 总页数

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    def to_dict(self):
        """转换为字典格式，支持JSON序列化"""
        return {
            "rows": self.rows,
            "total_records": self.total_records,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev
        }

    def __iter__(self):
        """使对象支持字典转换，便于JSON序列化"""
        for field, value in self.__dict__.items():
            if field not in ['has_next', 'has_prev']:
                yield field, value
        yield 'has_next', self.has_next
        yield 'has_prev', self.has_prev


# 标记
class BaseSchemas(PydanticBaseModel):
    """基础参数"""
    model_config = {"from_attributes": True, "populate_by_name": True}
    pass


class PaginationField(BaseSchemas):
    """分页参数"""
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=10, description="每页数量")

    @model_validator(mode='after')
    def validate_pagination(self):
        self.page = max(self.page, 1)
        self.page_size = max(self.page_size, 1)
        return self


# 分页参数：临时使用，后续统一分页入参数据，page_index page_size 改为 page page_size
class PaginationTmpField(BaseSchemas):
    """分页参数"""
    page_index: Optional[int] = Field(default=1, description="页码")
    page_size: Optional[int] = Field(default=10, description="每页数量")

    @model_validator(mode='after')
    def _validate_pagination(self):
        self.page_index = max(self.page_index, 1)
        self.page_size = max(self.page_size, 1)
        return self

