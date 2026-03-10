~~1、系统时间跨天的时候，日志新文件创建可能有问题~~
~~2、日志记录里面去掉登陆密码的记录~~
~~3、考虑在查询中实现分页和过滤，以减少查询的负担。~~
分页和过滤： 对于大型数据集，考虑在查询中实现分页和过滤，以减少查询的负担。FastAPI提供了易于使用的查询参数来处理分页和过滤。
from fastapi import Query

@app.get("/items/")
async def read_items(skip: int = Query(0, description="Skip items"), limit: int = Query(10, description="Limit items")):
   items = db.query(Item).offset(skip).limit(limit).all()
   return items

~~5、日志记录的分批写入避免频繁IO~~

~~6、日志的保留天数和大小设置~~

~~7、利用历史表进行审计功能，传入user~~

~~4、权限检查依赖注入 权限框架 自带缓存~~

~~8、使用 User(CoreModel): __abstract__ = True  定义所有基础权限相关的功能，提供给上层使用~~
~~使用的时候，通过一个子类生成器，处理需要实例化的子类~~

~~9、同8 创建同样的 自制架构相关的基础代码~~

~~10、 异常处理：Tenacity + 自定义异常类 + Rich ：Tenacity提供重试机制，Rich提供美观输出，自定义异常类提供业务语义。~~

11 跨域  ：协议、域名、端口 任何一个不同就构成跨域
Furion的CORS主要解决：

1. 开发效率 ：零配置跨域，开箱即用
2. Token认证 ：自动处理JWT Token传递
3. 预检优化 ：智能缓存预检请求，提升性能
4. SignalR支持 ：WebSocket跨域特殊处理
5. 安全性 ：生产环境精细控制访问源
6. 兼容性 ：处理移动端、桌面端各种特殊情况
   让开发者专注于业务逻辑，而不是花时间在跨域配置上。

12 HTTP 远程请求

13 事件总线


~~15 定时任务 (Schedule)~~

**16 虚拟文件系统**

~~审计日志~~

17 字段级权限 ：支持字段级别的权限控制

18 websocket 支持

# 项目命名备选：

### 1. Y-FastKit

* 简短易记
* 直观表达"FastAPI工具包"的概念
* 专业感强，符合Python生态命名习惯

### 2. Y-FastCore

* 突出"FastAPI核心功能"的定位
* 简洁有力
* 容易理解是基础功能库

19 一对多的主键关联必须 写明，而多对多不用 ，是否需要修改 ？参考 @yweb-core/examples/orm/create_demo_data.py 

20 expire_on_commit=False 是不安全的，在长链接 有可能造成脏数据，导致更新出问题，尤其是多对多关系
  # 创建SessionMaker
    SessionMaker = sessionmaker(
        autocommit=False,
        autoflush=True,
        bind=engine,
        expire_on_commit=False
    )
21 缓存模块提供查询已经缓存数据的 接口


前端 框架 ：
https://ui.mantine.dev/ 
https://mantine-boards.vercel.app/


# AI coding 模型对比：
Opus 4.6 慢 贵 做架构 特别复杂的 厉害一些，前端页面一般
GPT 5.3 codeX 快 性价比高、前端页面强，写测试更厉害，做架构差一点
Opus 4.5 比4.6略差一点，便宜一点，慢 ，可能是上下文少的原因

综合：
简单任务、前端页面、测试代码、review，GPT 5.3 codeX
复杂架构设计，Opus 4.6 或者 Opus 4.5