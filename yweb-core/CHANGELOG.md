# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.6] - 2026-10-15

### 修复
- 修复自增主键策略下 `before_insert` 事件重复处理主键的问题：`IdType.AUTO_INCREMENT` 时直接返回，由数据库在 INSERT 时生成主键，避免 Python 侧重复生成和多余的唯一性查询

## [0.1.5] - 2026-10-15

项目首次发布到 PyPI。

### 新增
- 完整的 FastAPI 基础框架：ORM、认证、中间件、缓存、调度器、存储等模块
- Agent 工具调用协议（FCL）：LLM 自由文本 → 结构化工具调用的解析与构建
- 包类型标记文件 `py.typed`，支持 mypy/pyright 类型识别

### 修复
- 修复打包时 README.md 未包含在 PyPI 展示中的问题（从外层复制到打包根目录）

### 已知问题
- `pyproject.toml` 中 `license` 字段使用了 TOML table 形式，setuptools ≥ 77 推荐改用 SPDX 字符串，2027-02-18 前需迁移
- License classifiers（`License :: OSI Approved :: MIT License`）已被弃用，需移除并改用 SPDX 表达式


