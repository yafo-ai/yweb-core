# YWeb 示例应用

这是一个完整的示例应用，演示如何使用 YWeb 基础类库。

## 运行示例

### 1. 安装依赖

```bash
# 在yweb根目录安装基础库
cd ../..
pip install -e .

# 返回demo_app目录安装其他依赖
cd examples/demo_app
pip install -r requirements.txt
```

### 2. 启动应用

```bash
python main.py
```

或使用uvicorn：

```bash
uvicorn main:app --reload
```

### 3. 访问应用

- 应用地址：http://localhost:8000
- API文档：http://localhost:8000/docs
- ReDoc文档：http://localhost:8000/redoc

## 示例接口

### 1. 根路径

```bash
curl http://localhost:8000/
```

### 2. 获取用户列表（分页）

```bash
curl "http://localhost:8000/users?page=1&page_size=10"
```

### 3. 获取单个用户

```bash
curl http://localhost:8000/users/1
```

### 4. 创建用户

```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob", "email": "bob@example.com"}'
```

### 5. 登录示例

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'
```

### 6. 批量导入（警告响应）

```bash
curl -X POST http://localhost:8000/batch-import \
  -H "Content-Type: application/json" \
  -d '[{"name": "User1"}, {"name": ""}, {"name": "User2"}]'
```

## 功能演示

### ✅ 统一响应格式

所有接口都返回统一的响应格式：

```json
{
    "status": "success",
    "message": "响应消息",
    "msg_details": [],
    "data": {}
}
```

### ✅ 请求日志

每个请求都会记录详细的日志信息，包括：
- 请求ID
- 处理时间
- 请求方法和URL
- 客户端IP
- 响应状态码

### ✅ 性能监控

超过1秒的请求会自动记录警告日志。

### ✅ 分页支持

用户列表接口演示了如何使用分页功能。

### ✅ 错误处理

演示了如何返回各种错误响应（400, 404等）。

### ✅ 警告响应

批量导入接口演示了如何返回带警告的成功响应。

### ✅ 密码加密

登录接口演示了密码哈希和验证功能。

## 学习建议

1. 先查看 `main.py` 了解整体结构
2. 尝试调用各个接口，观察响应格式
3. 查看日志输出，了解中间件的工作方式
4. 修改代码，尝试添加新功能
5. 参考完整文档了解更多高级用法

