"""
ACL 模块基础示例

演示 ACL 模块的基本用法：创建模型、注册资源、配置规则、检查权限。
"""

from fastapi import FastAPI

from yweb.orm import init_database
from yweb.acl import setup_acl


def main():
    app = FastAPI()

    # 初始化数据库
    init_database("sqlite:///acl_demo.db")

    # 一站式设置 ACL
    acl = setup_acl(app=app, table_prefix="sys_")
    service = acl.get_service()

    # ---------- 注册资源树 ----------

    # 根文件夹
    root = service.register_resource(
        resource_type="FOLDER",
        resource_id="f001",
        display_name="技术文档",
    )

    # 子文档
    service.register_resource(
        resource_type="DOCUMENT",
        resource_id="d001",
        display_name="API 设计规范",
        parent_id=root.id,
    )
    service.register_resource(
        resource_type="DOCUMENT",
        resource_id="d002",
        display_name="架构文档",
        parent_id=root.id,
    )

    # ---------- 配置权限规则 ----------

    # 技术部门可以读文件夹（继承到子资源）
    service.create_rule(
        resource_type="FOLDER",
        resource_id="f001",
        subject_id="dept:tech",
        permission_level=10,  # READ
        effect="ALLOW",
        inherit=True,
        subject_type="dept",
    )

    # 张三可以编辑 d001
    service.create_rule(
        resource_type="DOCUMENT",
        resource_id="d001",
        subject_id="user:zhangsan",
        permission_level=30,  # WRITE
        effect="ALLOW",
    )

    # ---------- 检查权限 ----------

    # 张三的身份标签（应用层展开）
    zhangsan_ids = {"user:zhangsan", "dept:tech", "everyone"}

    # 张三能读 d001 吗？→ True（dept:tech 继承 + 自身 WRITE）
    print("张三读 d001:", service.check(zhangsan_ids, "DOCUMENT", "d001", 10))

    # 张三能写 d001 吗？→ True（直接授权 WRITE=30）
    print("张三写 d001:", service.check(zhangsan_ids, "DOCUMENT", "d001", 30))

    # 张三能读 d002 吗？→ True（dept:tech 从 f001 继承）
    print("张三读 d002:", service.check(zhangsan_ids, "DOCUMENT", "d002", 10))

    # 李四（无部门）能读 d001 吗？→ False
    lisi_ids = {"user:lisi", "everyone"}
    print("李四读 d001:", service.check(lisi_ids, "DOCUMENT", "d001", 10))

    # 获取有效权限等级
    level = service.get_effective_level(zhangsan_ids, "DOCUMENT", "d001")
    print(f"张三对 d001 的有效等级: {level}")


if __name__ == "__main__":
    main()
