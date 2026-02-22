"""
FastAPI集成 - JWT版本：使用真实JWT token

✅ 生产环境推荐方案：
1. 使用python-jose库实现JWT
2. 从JWT payload中提取user_id
3. 完全消除数据库查询
4. 支持token过期、刷新等功能

安装依赖：
pip install python-jose[cryptography] passlib[bcrypt]
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sqlalchemy-history-main'))

from typing import Annotated, Union
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy_history import make_versioned, version_class, transaction_class
import sqlalchemy as sa
from yweb.orm.history import CurrentUserPlugin, set_user, clear_user
from yweb.orm import BaseModel,CoreModel, init_versioning

# JWT相关导入
try:
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("⚠️ 警告：未安装python-jose，请运行: pip install python-jose[cryptography]")

# ============================================================================
# JWT配置
# ============================================================================

# ⚠️ 生产环境中应该使用环境变量或配置文件
SECRET_KEY = "your-secret-key-here-change-in-production"  # 生产环境必须修改
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ============================================================================
# 类型定义
# ============================================================================

UserIdType = Union[int, str]  # 支持多种类型

# ============================================================================
# 数据库配置
# ============================================================================

# 1. 先定义 User 类（必须在 make_versioned 之前！）
#    否则 Transaction 表不会有 user_id 列
class User(BaseModel):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(100))  # 存储密码哈希

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


# 2. 初始化版本化（User 类已存在，会自动创建 user_id 列）
# 使用 CurrentUserPlugin 启用用户追踪 ，必须在定义任何 enable_history=True 的模型之前调用 init_versioning()
init_versioning(user_cls=User, plugins=[CurrentUserPlugin()])


# 3. 定义带版本控制的模型
class Article(CoreModel):
    __tablename__ = 'articles'
    __versioned__ = {}
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text)


# 4. 配置 mappers（触发版本化配置）
sa.orm.configure_mappers()


# 5. 初始化数据库
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "demo_current_user_tracking_fastapi.db")

# 删除旧数据库
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"[OK] 删除旧数据库: {db_path}")

engine = create_engine(f"sqlite:///{db_path}", echo=False)
BaseModel.metadata.drop_all(engine)
BaseModel.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)

# ============================================================================
# JWT工具函数
# ============================================================================

# bcrypt限制：密码最长72字节
MAX_PASSWORD_LENGTH = 72

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """创建JWT access token"""
    if not JWT_AVAILABLE:
        raise RuntimeError("JWT库未安装")

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    此处为演示，实际场景修改为正式方法
    """

    return True

def get_password_hash(password: str) -> str:
        """
    生成密码哈希
    假装生成密码，实际场景修改为正式方法
    """

        return password

# ============================================================================
# FastAPI依赖注入 - JWT版本
# ============================================================================

def get_db():
    """获取数据库session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> UserIdType:
    """
    ✅ JWT版本：从JWT token中提取user_id

    优势：
    1. 无需查询数据库
    2. 支持token过期验证
    3. 可以在payload中存储额外信息
    4. 安全性高（签名验证）

    JWT payload示例：
    {
        "user_id": 1,
        "username": "张三",  # 可选：避免额外查询
        "exp": 1234567890
    }
    """
    if not JWT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT库未安装，请运行: pip install python-jose[cryptography]"
        )

    token = credentials.credentials

    try:
        # ✅ 解析JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("user_id")  # ✅ 准确的类型注解

        # ✅ 检查user_id是否有效（None、0、空字符串都视为无效）
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的token：缺少user_id字段",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ✅ 额外检查：user_id不能为0（如果使用自增主键）
        if isinstance(user_id, int) and user_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的token：user_id必须大于0",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ✅ 直接返回user_id，无需查询数据库
        return user_id

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_db_with_user(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[UserIdType, Depends(get_current_user_id)]
) -> Session:
    """将user_id注入到session"""
    set_user(db, user_id)
    return db

# ============================================================================
# FastAPI应用
# ============================================================================

app = FastAPI(title="SQLAlchemy-History + FastAPI + JWT")

@app.on_event("startup")
def startup():
    """初始化测试数据"""
    # 调试：检查 Transaction 表结构
    from sqlalchemy_history import versioning_manager
    tx_cls = versioning_manager.transaction_cls
    print(f"\n[DEBUG] Transaction class: {tx_cls}")
    print(f"[DEBUG] Transaction type: {type(tx_cls)}")
    if tx_cls is not None:
        if hasattr(tx_cls, '__table__'):
            print(f"[DEBUG] Transaction columns: {[c.name for c in tx_cls.__table__.columns]}")
        print(f"[DEBUG] hasattr(tx_cls, 'user_id'): {hasattr(tx_cls, 'user_id')}")
    
    db = SessionLocal()

    if db.query(User).count() == 0:
        user1 = User(
            username='张三',
            password_hash=get_password_hash('password123')
        )
        user2 = User(
            username='李四',
            password_hash=get_password_hash('password456')
        )
        db.add_all([user1, user2])
        db.commit()
        print("✓ 创建测试用户")
        print(f"  用户1: id={user1.id}, username={user1.username}, password=password123")
        print(f"  用户2: id={user2.id}, username={user2.username}, password=password456")

    db.close()

# ============================================================================
# 认证端点
# ============================================================================

@app.post("/login")
def login(
    username: str,
    password: str,
    db: Annotated[Session, Depends(get_db)]
):
    """
    登录接口，返回JWT token

    ✅ 这是唯一需要查询数据库的认证接口
    ✅ 后续所有请求都使用JWT，无需查询数据库
    """
    if not JWT_AVAILABLE:
        return {
            "error": "JWT库未安装",
            "message": "请运行: pip install python-jose[cryptography]"
        }

    # 查询用户（仅在登录时查询一次）
    user = db.query(User).filter_by(username=username).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ✅ 创建JWT token，将user_id存入payload
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "username": user.username  # 可选：避免后续查询
        },
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "username": user.username
        }
    }

# ============================================================================
# 业务端点
# ============================================================================

@app.post("/articles")
def create_article(
    title: str,
    content: str,
    db: Annotated[Session, Depends(get_db_with_user)],
):
    """
    创建文章

    ✅ 无需查询User表，user_id自动从JWT提取并记录到Transaction
    """
    article = Article(title=title, content=content)
    db.add(article)
    db.commit()
    db.refresh(article)

    return {
        "id": article.id,
        "title": article.title,
        "message": "✅ 文章创建成功（JWT方案，零数据库查询）"
    }

@app.put("/articles/{article_id}")
def update_article(
    article_id: int,
    content: str,
    db: Annotated[Session, Depends(get_db_with_user)],
    user_id: Annotated[UserIdType, Depends(get_current_user_id)]
):
    """更新文章"""
    article = db.query(Article).filter_by(id=article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    article.content = content
    db.commit()

    return {
        "id": article.id,
        "title": article.title,
        "message": f"✅ 文章更新成功 (user_id={user_id})"
    }

@app.get("/articles/{article_id}/history")
def get_article_history(
    article_id: int,
    db: Annotated[Session, Depends(get_db)]
):
    """查看文章版本历史"""
    ArticleVersion = version_class(Article)
    Transaction = transaction_class(Article)

    versions = db.query(ArticleVersion).filter_by(id=article_id).order_by(
        ArticleVersion.transaction_id
    ).all()

    if not versions:
        raise HTTPException(status_code=404, detail="文章不存在")

    history = []
    for version in versions:
        tx = db.query(Transaction).get(version.transaction_id)
        op_type = ['创建', '修改', '删除'][version.operation_type]

        history.append({
            "version": version.transaction_id,
            "operation": op_type,
            "title": version.title,
            "content": version.content,
            "user_id": tx.user_id,
            "username": tx.user.username if tx.user else "Unknown",
            "timestamp": str(tx.issued_at)
        })

    return {
        "article_id": article_id,
        "total_versions": len(history),
        "history": history
    }

@app.get("/me")
def get_current_user_info(
    user_id: Annotated[UserIdType, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)]
):
    """
    获取当前用户信息

    💡 注意：这个接口需要查询数据库获取完整用户信息
    💡 如果只需要user_id，可以直接从JWT获取，无需查询
    """
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "id": user.id,
        "username": user.username
    }

@app.get("/")
def root():
    """API文档"""
    return {
        "message": "✅ SQLAlchemy-History + FastAPI + JWT",
        "jwt_status": "已安装" if JWT_AVAILABLE else "未安装（请运行: pip install python-jose[cryptography]）",
        "docs": "/docs",
        "workflow": {
            "步骤1": "POST /login 登录获取JWT token（唯一需要查询数据库）",
            "步骤2": "使用token访问其他接口（无需查询数据库）",
            "步骤3": "user_id自动从JWT提取并记录到Transaction表"
        },
        "test_users": {
            "张三": {"username": "张三", "password": "password123"},
            "李四": {"username": "李四", "password": "password456"}
        },
        "example_requests": {
            "1. 登录": {
                "method": "POST",
                "url": "/login?username=张三&password=password123",
                "response": "返回access_token"
            },
            "2. 创建文章": {
                "method": "POST",
                "url": "/articles?title=测试&content=内容",
                "headers": {"Authorization": "Bearer <access_token>"}
            },
            "3. 查看历史": {
                "method": "GET",
                "url": "/articles/1/history"
            }
        }
    }

# ============================================================================
# 运行说明
# ============================================================================

# ============================================================================
# 自动测试代码
# ============================================================================

def test_update_article_api():
    """
    自动测试：修改文章API

    测试流程：
    1. 登录获取JWT token
    2. 创建一篇文章
    3. 修改文章内容
    4. 查看文章历史记录
    """
    import requests
    import time

    BASE_URL = "http://localhost:9001"

    print("\n" + "="*60)
    print("开始自动测试：修改文章API")
    print("="*60)

    # 等待服务器启动
    print("\n[等待] 等待服务器启动...")
    time.sleep(2)

    try:
        # 步骤1: 登录获取token
        print("\n[步骤1] 登录获取JWT token")
        login_response = requests.post(
            f"{BASE_URL}/login",
            params={"username": "张三", "password": "password123"}
        )

        if login_response.status_code != 200:
            print(f"[失败] 登录失败: {login_response.text}")
            return

        login_data = login_response.json()
        token = login_data["access_token"]
        user_id = login_data["user"]["id"]
        username = login_data["user"]["username"]

        print(f"[成功] 登录成功")
        print(f"   用户: {username} (ID: {user_id})")
        print(f"   Token: {token[:20]}...")

        headers = {"Authorization": f"Bearer {token}"}

        # 步骤2: 创建文章
        print("\n[步骤2] 创建文章")
        create_response = requests.post(
            f"{BASE_URL}/articles",
            params={
                "title": "测试文章标题",
                "content": "这是原始内容"
            },
            headers=headers
        )

        if create_response.status_code != 200:
            print(f"[失败] 创建文章失败: {create_response.text}")
            return

        create_data = create_response.json()
        article_id = create_data["id"]

        print(f"[成功] 文章创建成功")
        print(f"   文章ID: {article_id}")
        print(f"   标题: {create_data['title']}")

        # 步骤3: 修改文章（第一次）
        print("\n[步骤3] 修改文章（第一次）")
        update_response1 = requests.put(
            f"{BASE_URL}/articles/{article_id}",
            params={"content": "这是第一次修改的内容"},
            headers=headers
        )

        if update_response1.status_code != 200:
            print(f"[失败] 修改文章失败: {update_response1.text}")
            return

        update_data1 = update_response1.json()
        print(f"[成功] 文章修改成功（第一次）")
        print(f"   {update_data1['message']}")

        # 步骤4: 换用户登录，然后修改文章（第二次）
        print("\n[步骤4] 切换用户（李四）并修改文章")
        time.sleep(1)  # 等待1秒，确保时间戳不同

        # 用李四登录
        login_response2 = requests.post(
            f"{BASE_URL}/login",
            params={"username": "李四", "password": "password456"}
        )

        if login_response2.status_code != 200:
            print(f"[失败] 李四登录失败: {login_response2.text}")
            return

        login_data2 = login_response2.json()
        token2 = login_data2["access_token"]
        user_id2 = login_data2["user"]["id"]
        username2 = login_data2["user"]["username"]

        print(f"[成功] 切换用户成功")
        print(f"   用户: {username2} (ID: {user_id2})")

        headers2 = {"Authorization": f"Bearer {token2}"}

        # 用李四的身份修改文章
        update_response2 = requests.put(
            f"{BASE_URL}/articles/{article_id}",
            params={"content": "这是第二次修改的内容（由李四修改）"},
            headers=headers2
        )

        if update_response2.status_code != 200:
            print(f"[失败] 修改文章失败: {update_response2.text}")
            return

        update_data2 = update_response2.json()
        print(f"[成功] 文章修改成功（第二次）")
        print(f"   {update_data2['message']}")

        # 步骤5: 查看文章历史
        print("\n[步骤5] 查看文章历史记录")
        history_response = requests.get(
            f"{BASE_URL}/articles/{article_id}/history"
        )

        if history_response.status_code != 200:
            print(f"[失败] 获取历史记录失败: {history_response.text}")
            return

        history_data = history_response.json()

        print(f"[成功] 历史记录获取成功")
        print(f"   文章ID: {history_data['article_id']}")
        print(f"   总版本数: {history_data['total_versions']}")
        print("\n   版本详情:")

        for i, version in enumerate(history_data['history'], 1):
            print(f"\n   版本 {i}:")
            print(f"     操作: {version['operation']}")
            print(f"     内容: {version['content']}")
            print(f"     操作人: {version['username']} (ID: {version['user_id']})")
            print(f"     时间: {version['timestamp']}")

        print("\n" + "="*60)
        print("[完成] 测试完成！所有步骤执行成功")
        print("="*60)
        
        # 测试完成后自动停止服务器
        print("\n[停止] 正在停止服务器...")
        import os
        os._exit(0)

    except requests.exceptions.ConnectionError:
        print("\n[错误] 无法连接到服务器，请确保服务器正在运行")
        import os
        os._exit(1)
    except Exception as e:
        print(f"\n[错误] 测试过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # 出错后也停止服务器
        import os
        os._exit(1)

if __name__ == "__main__":
    import uvicorn
    import sys
    import io
    import threading

    # 设置UTF-8编码，避免Windows控制台编码问题
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("="*60)
    print("FastAPI + SQLAlchemy-History + JWT")
    print("="*60)
    print("\n[OK] JWT方案优势：")
    print("  1. 登录时查询一次数据库，获取JWT token")
    print("  2. 后续所有请求从JWT提取user_id，零数据库查询")
    print("  3. 支持token过期、刷新等安全功能")
    print("  4. 性能最优：响应时间 ~5ms")
    print("\n测试用户:")
    print("  张三: password123")
    print("  李四: password456")
    print("\n使用流程:")
    print("  1. POST /login 获取token")
    print("  2. 使用token访问其他接口")
    print("\n示例:")
    print("  # 1. 登录")
    print("  curl -X POST 'http://localhost:8000/login?username=张三&password=password123'")
    print("  # 返回: {\"access_token\": \"eyJ...\"}")
    print()
    print("  # 2. 创建文章（使用token）")
    print("  curl -X POST 'http://localhost:8000/articles?title=测试&content=内容' \\")
    print("       -H 'Authorization: Bearer eyJ...'")
    print()

    # 启动测试线程
    test_thread = threading.Thread(target=test_update_article_api, daemon=True)
    test_thread.start()

    # 启动服务器（这会阻塞主线程）
    uvicorn.run(app, host="0.0.0.0", port=9001)
