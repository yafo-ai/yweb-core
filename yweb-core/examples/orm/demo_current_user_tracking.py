"""当前用户追踪演示

本脚本演示了 yweb.orm 的当前用户追踪功能，实现历史记录审计。

运行方式：
    cd yweb-core/examples/orm
    python demo_current_user_tracking.py
"""

import os
import sys

# 确保可以导入 yweb
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy import Column, String, Text, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, configure_mappers
from sqlalchemy_history import make_versioned, version_class, versioning_manager

# ============================================================================
# 1. 初始化版本化（必须在定义模型之前）
# ============================================================================

from yweb.orm.history import CurrentUserPlugin, set_user, clear_user
from yweb.orm import BaseModel,CoreModel, init_versioning
from yweb.orm import init_database


# ============================================================================
# 2. 定义模型
# ============================================================================



class MyUser(BaseModel):
    """用户模型（不启用版本控制）"""
    __tablename__ = 'demo_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)

# 如果需要使用自定义主键策略（如短UUID），必须在 init_versioning() 之前配置
# 
# 使用 CurrentUserPlugin 启用用户追踪 ，必须在定义任何 enable_history=True 的模型之前调用
init_versioning(user_cls=MyUser, plugins=[CurrentUserPlugin()])



class Article(CoreModel):
    """文章模型（启用版本控制）"""
    __tablename__ = 'demo_articles'
    enable_history=True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    status = Column(String(20), default='draft')


print("[OK] 版本化初始化成功（已启用 CurrentUserPlugin）")
# 配置 mappers（必须在创建表之前）
configure_mappers()
print("[OK] Mappers 配置完成")

# ============================================================================
# 3. 初始化数据库
# ============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "demo_current_user_tracking.db")

# 删除旧数据库
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"[OK] 删除旧数据库: {db_path}")


engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)

CoreModel.query = session_scope.query_property()

session = session_scope()
# 配置 mappers（必须在创建表之前）
try:
    configure_mappers()
    print("[OK] Mappers 配置完成")
except Exception as e:
    print(f"[ERROR] Mappers 配置失败: {e}")


# 清空并重建数据表
print("[OK] 清空并重建数据表...")
BaseModel.metadata.drop_all(engine)
BaseModel.metadata.create_all(engine)

# ============================================================================
# 4. 辅助函数
# ============================================================================




def print_history(session, article_id):
    """打印文章的版本历史"""
    ArticleVersion = version_class(Article)
    Transaction = versioning_manager.transaction_cls
    
    versions = session.query(ArticleVersion).filter_by(id=article_id).order_by(
        ArticleVersion.transaction_id
    ).all()
    
    print(f"\n  文章 ID={article_id} 的版本历史:")
    print(f"  {'─'*50}")
    
    for v in versions:
        # 检查 Transaction 是否已经是真正的模型类（有 __table__ 属性）
        if Transaction and hasattr(Transaction, '__table__'):
            tx = session.query(Transaction).filter_by(id=v.transaction_id).first()
        else:
            tx = None
        op_type = ['创建', '修改', '删除'][v.operation_type]
        user_id = tx.user_id if tx else 'N/A'
        
        print(f"  版本 {v.transaction_id}:")
        print(f"    操作: {op_type}")
        print(f"    标题: {v.title}")
        print(f"    内容: {v.content[:30]}..." if v.content and len(v.content) > 30 else f"    内容: {v.content}")
        print(f"    状态: {v.status}")
        print(f"    操作人 user_id: {user_id}")
        print()


# ============================================================================
# 5. 测试场景
# ============================================================================

def test_scenario_1():
    """场景1：用户1创建文章，用户2修改"""
    print("场景1：多用户操作追踪")
    
    # 用户1创建文章
    print("  [用户1] 创建文章...")
    set_user(session, 1)
    
    article = Article(title="测试文章", content="原始内容", status="draft")
    article.add(True)
    article_id = article.id
    
    clear_user(session)
    print(f"  [OK] 文章创建成功: ID={article_id}")
    
    # 用户2修改文章
    print("  [用户2] 修改文章...")
    set_user(session, 2)
    
    article.content = "用户2修改的内容"
    article.status = "review"
    article.save(True)
    
    clear_user(session)
    print("  [OK] 文章修改成功")
    
    # 用户3发布文章
    print("  [用户3] 发布文章...")
    set_user(session, 3)
    
    article.status = "published"
    article.save(True)
    
    clear_user(session)
    print("  [OK] 文章发布成功")
    
    # 打印历史
    print_history(session, article_id)
    
    return article_id


def test_scenario_2():
    """ 版本4：无用户追踪"""
    print(" 版本4：无用户追踪（user_id=None）")
    
    clear_user(session)
    
    print("  [匿名] 创建文章（未设置 user_id）...")
    article = Article(title="匿名文章", content="没有追踪操作者")
    article.add(True)
    article_id = article.id
    
    print(f"  [OK] 文章创建成功: ID={article_id}")
    print_history(session, article_id)
    
    return article_id


def test_scenario_3():
    """ 版本5：系统用户（后台任务）"""
    print(" 版本5：系统用户（后台任务场景）")
    
    SYSTEM_USER_ID = 0
    
    print(f"  [系统用户 ID={SYSTEM_USER_ID}] 执行自动归档任务...")
    set_user(session, SYSTEM_USER_ID)
    
    article = Article(title="自动归档", content="系统自动执行", status="archived")
    article.add(True)
    article_id = article.id
    
    clear_user(session)
    print(f"  [OK] 任务完成: ID={article_id}")
    print_history(session, article_id)
    
    return article_id




def show_fastapi_example():
    """展示 FastAPI 集成示例"""
    print("FastAPI 集成示例")
    
    code = '''
from fastapi import FastAPI
from sqlalchemy_history import make_versioned
from yweb.orm.history import CurrentUserPlugin, set_current_user_id
from yweb.auth import JWTManager
from yweb.middleware import CurrentUserMiddleware

# 1. 初始化版本化（必须在定义模型之前）
make_versioned(plugins=[CurrentUserPlugin()])

# 2. 定义模型...（省略）

# 3. 创建 FastAPI 应用
app = FastAPI()

# 4. 配置中间件（自动从 JWT 提取 user_id）
jwt_manager = JWTManager(secret_key="your-secret-key")
app.add_middleware(
    CurrentUserMiddleware,
    jwt_manager=jwt_manager,
    skip_paths=["/login", "/docs"]
)

# 5. 业务代码（user_id 自动追踪，零改动！）
@app.post("/articles")
def create_article(title: str, content: str, db: Session = Depends(get_db)):
    article = Article(title=title, content=content)
    db.add(article)
    db.commit()  # ✅ user_id 自动记录到 Transaction 表
    return {"id": article.id}
'''
    print(code)


# ============================================================================
# 主函数
# ============================================================================

def main():
    print("\n" + "="*60)
    print("  当前用户追踪功能演示")
    print("="*60)
    
    
    show_fastapi_example()
    
    # 创建测试用户
    user1 = MyUser(username='用户1')
    user2 = MyUser(username='用户2')
    user3 = MyUser(username='用户3')
    MyUser.add_all([user1, user2, user3], commit=True)
    print("\n[OK] 测试用户创建完成")
    
    
    # 运行测试场景
    test_scenario_1()
    test_scenario_2()
    test_scenario_3()
    
    print("演示完成")
    print("[OK] 所有场景执行成功！")
    print(f"\n数据库文件: {db_path}")
        



if __name__ == "__main__":
    main()
