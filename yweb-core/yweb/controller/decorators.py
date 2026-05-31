"""
控制器装饰器 —— 用于标记方法的 HTTP 方法。

ResourceController 中所有 public 方法默认注册为 POST。
使用 @get 标记需要注册为 GET 的方法。
"""


def get(func):
    """标记该方法为 GET 端点（默认是 POST）"""
    func._http_method = "GET"
    return func
