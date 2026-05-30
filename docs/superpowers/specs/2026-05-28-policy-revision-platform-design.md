# 企业制度修订管理平台 — 设计规格书

> **状态:** 已批准 · v1 已实现  
> **日期:** 2026-05-28  
> **范围:** v1 — 内部制度起草与按意见改稿（私有化部署 + LLM 辅助）

---

## 1. 背景与目标

### 1.1 问题陈述

大型企业现行制度管理手段陈旧，**制度更新**依赖大量手工操作。核心痛点集中在：

1. **起草（A）** — 从旧版或空白改写耗时长，难以对齐变更意图。  
2. **按意见改稿（D）** — 评审意见分散，逐条落实到正文困难，易遗漏。

现行流程（用户确认）：

```text
归口部门起草 → 征求相关部门负责人意见 → 收集评审 → 按意见修改 → 发布新版本
```

文档习惯：**Word/WPS 起草**；系统内 **Markdown + 流程图（Mermaid）**；正式发布 **PDF**。部署：**私有化 / 内网**。

### 1.2 v1 目标

| 目标 | 说明 |
|------|------|
| **减手工** | 意见集中管理；LLM 辅助初稿与逐条改稿建议 |
| **可审计** | 意见 → 处理决定 → 文本变更 → 发布 PDF 全链路留痕 |
| **快** | 异步文档转换与分段 LLM；检索 v1 用 PostgreSQL 全文 |
| **安全** | 私有化；RBAC；模型调用仅经内网网关；人工确认所有 AI 输出 |

### 1.3 v1 明确不做

- 外规自动监控与抓取比对  
- 义务合规矩阵、Evidence 台账  
- 千万级文档 RAG 问答（见 Phase 2，参考仓库 `reference/` RAG 文章）

---

## 2. 产品范围与角色

### 2.1 功能清单（v1）

1. **制度库** — 分类、归口部门、现行/历史版本、生效/废止日期  
2. **修订任务（Revision）** — 单次制度从 vN → vN+1 的完整协作  
3. **结构化正文** — Canonical Markdown + 稳定 `section_id`；Mermaid 流程图  
4. **格式流水线** — docx 导入/导出；发布 PDF；不可变归档  
5. **征求意见** — 指定评审人；意见锚定章节；状态跟踪  
6. **LLM 辅助** — 初稿生成；意见→修改建议；全部意见关闭方可进入发布  
7. **发布** — PDF 正式版；旧版 superseded  
8. **安全** — LDAP/AD、RBAC、审计日志、内网 LLM 网关  

### 2.2 角色

| 角色 | 典型用户 | 权限摘要 |
|------|----------|----------|
| 制度经办（Owner） | 归口部门 | 发起修订、编辑草稿、提交征求意见、处理 LLM 建议 |
| 评审人（Reviewer） | 相关部门负责人 | 提交意见；不可发布 |
| 制度管理员（Policy admin） | 合规/制度管理 | 配置流程模板、发布、废止、授权 |
| 阅读者（Reader） | 全员或范围用户 | 只读已发布版本 |
| 系统管理员 | IT | 部署、模型配置、备份 |

### 2.3 成功标准（试点）

- 评审意见不再依赖邮件/微信散落传递  
- 起草与改稿人工编辑时间显著下降（试点调研，目标如节省 30%+）  
- 任意发布版本可还原：意见列表 + 采纳记录 + PDF + MD 快照  

---

## 3. 架构与部署

### 3.1 推荐方案：模块化单体（Modular monolith）

**技术栈（建议）：**

| 层 | 选型 |
|----|------|
| 前端 | React SPA（中文 UI） |
| API | FastAPI，模块：`auth`, `policies`, `workflow`, `ai`, `export` |
| 数据库 | PostgreSQL |
| 对象存储 | MinIO（或企业兼容 S3） |
| 队列 | Redis + Celery/ARQ worker |
| 反向代理 | Nginx + 企业 TLS 证书 |
| LLM | OpenAI 兼容内网网关（如 `XIAOMI_BASE_URL`） |

### 3.2 拓扑

```text
浏览器 (HTTPS) → Nginx → Web SPA + API
                              ↓
            PostgreSQL / Redis / MinIO / Worker → 内网 LLM 网关
```

### 3.3 交付物

- Docker Compose 或 Helm chart（`deploy/`）  
- 配置分环境：`dev` / `staging` / `prod`  
- 密钥：生产使用 K8s Secret / 企业密钥管理；禁止将真实 API Key 提交仓库  

### 3.4 扩展路线

| 阶段 | 内容 |
|------|------|
| v1 | 本规格 |
| v1.1 | 钉钉/飞书通知与 SSO；Elasticsearch 中文检索 |
| v2 | 制度库 RAG 问答；外规关联 |

### 3.5 集成预留

- REST API + Webhook：`revision.published`  
- v1 认证：LDAP/AD  

---

## 4. 文档模型与格式流水线

### 4.1  Canonical 存储

- **Markdown + YAML front matter**（`policy_id`, `title`, `version`, `effective_date`, `owner_dept`, `status`）  
- **章节树 JSON** — 由标题解析；每节稳定 `{#section_id}`  
- **对象存储** — docx 原件、PDF 发布件、MD 里程碑快照；DB 存指针与 `content_sha256`  

### 4.2 格式流

| 方向 | 行为 |
|------|------|
| docx → md | 修订开始时上传；worker 转换；保留原 docx |
| 系统内编辑 | 主路径；MD 编辑器 + Mermaid 预览 |
| 离线 Word | 导出 docx → 再导入 → 三路对比（canonical / 导入 / 合并建议） |
| md → pdf | 仅发布步骤；封面、页眉页脚、版本号、可选水印 |
| md → docx | 供坚持 Word 的评审人；系统内意见仍优先 |

### 4.3 版本规则

- **Policy** — 逻辑制度一条  
- **Version** — 仅一个 **current published**  
- **Revision draft** — 一次修订任务一个活跃工作稿  
- **已发布 PDF** — 不可变对象  

### 4.4 v1 不做

- OnlyOffice 实时协同编辑  
- 复杂版式 100% docx 还原（需在导出说明中标注限制）  

---

## 5. 工作流与评审

### 5.1 修订任务状态机

```text
DRAFT → IN_CONSULTATION → IN_REVISION → PENDING_PUBLISH → PUBLISHED
                                              ↘ CANCELLED（发布前任意阶段）
```

- v1 支持管理员 **重新打开征求意见**（第二轮），不实现任意复杂 BPMN。  

### 5.2 评审人

- 手工指定用户/部门负责人  
- **制度类型模板**（管理员配置默认评审人列表）  
- **Mandatory / FYI** — 发布门禁仅检查 mandatory 已反馈  

### 5.3 意见模型

| 字段 | 说明 |
|------|------|
| `section_id` | 锚定章节 |
| `body` | 意见正文 |
| `status` | open / accepted / rejected / deferred |
| `resolution_note` | 不采纳/暂缓时必填 |
| `llm_suggestion_id` | 可选关联 AI 建议 |

**门禁：** 存在 `open` 意见不可进入 `PENDING_PUBLISH`；`rejected`/`deferred` 须有说明。

### 5.4 通知（v1 最小）

- 站内待办 + 内网 SMTP 邮件  
- 未反馈提醒（定时任务）  
- 钉钉/飞书 → v1.1  

### 5.5 权限矩阵（摘要）

| 操作 | Owner | Reviewer | Policy admin |
|------|-------|----------|--------------|
| 编辑草稿 | DRAFT / IN_REVISION | ✗ | ✗ |
| 提交意见 | ✗ | IN_CONSULTATION | ✗ |
| 发布 | ✗ | ✗ | ✓ |

---

## 6. LLM 设计

### 6.1 原则

- 人工确认所有建议；禁止自动发布  
- 上下文仅含：当前稿、变更说明、目标章节、用户勾选附件摘录  
- 不编造法规条文；法律结论由人负责  
- 全量审计：模板版本、输入 hash、模型、输出、采纳人  

### 6.2 能力

| 能力 | 触发 | 输出 |
|------|------|------|
| **初稿生成** | DRAFT 中「生成初稿」 | 按 `section_id` 的 replace/insert/delete 建议 |
| **意见→改稿** | 单条或批量未关闭意见 | 章节级 suggested_markdown + diff 摘要 |
| **发布门禁** | 非 LLM | 意见全部关闭 + 管理员复核（可选勾选） |

辅助（可选 v1）：术语一致性警告；修订摘要供邮件（人工改后发送）。

### 6.3 工程

- `apps/api/ai/` — client、版本化 prompt YAML、guardrails、异步 job  
- 长文按 section 分段调用 worker  
- 低温、JSON schema 校验、每用户并发 1 个 LLM 任务、租户日 token 上限  

### 6.4 Phase 2

- 跨制度库 RAG（混合检索、引用溯源），对齐仓库 RAG 参考架构  

---

## 7. 安全与非功能需求

### 7.1 安全

| 项 | 要求 |
|----|------|
| 部署 | 私有化；数据与模型调用不出公网 |
| 传输 | TLS（企业 CA） |
| 认证 | LDAP/AD；服务端 session/JWT |
| 授权 | RBAC + 资源级（制度/修订任务） |
| 审计 | 追加写；含工作流转移、意见处理、LLM 采纳、发布 |
| 密钥 | 环境变量/密钥管理；轮换；禁止入库 |
| 备份 | PG 定期备份 + 对象存储版本；灾难恢复 RPO/RTO 由 IT 定义 |

### 7.2 性能（v1 目标量级）

| 指标 | 目标 |
|------|------|
| 制度总量 | 数百～数千 |
| 并行修订任务 | 数十 |
| API 常规操作 | P95 < 500ms（不含 LLM） |
| docx 转换 / PDF | 异步，进度可查 |
| LLM 单节 | < 60s P95（依赖内网模型） |

### 7.3 可用性与运维

- 健康检查 `/health`  
- 结构化日志（request_id、revision_id）  
- 指标：LLM token、队列深度、转换失败率  

### 7.4 合规与内容

- 正式发布以 **PDF** 为准  
- 水印、版本号、生效日期在 PDF 模板可配置  
- 个人敏感信息：可选在送 LLM 前脱敏（v1.1 增强）  

---

## 8. 仓库结构（建议）

```text
easy-regulations/
  apps/web/
  apps/api/
  apps/worker/
  packages/shared/
  deploy/
  docs/superpowers/specs/   # 本文档
  docs/superpowers/plans/   # 实施计划（下一步）
```

---

## 9. 已确认的设计决策（评审记录）

| § | 主题 | 状态 |
|---|------|------|
| 1 | 范围与角色 | 已确认 |
| 2 | 架构与私有化部署 | 已确认 |
| 3 | 文档模型与格式 | 已确认 |
| 4 | 工作流与评审 | 已确认 |
| 5 | LLM | 已确认 |
| 6 | 安全与非功能 | 已确认 |

---

## 10. 下一步

1. 确认 §6（安全与非功能）  
2. 评审通过后，使用 **writing-plans** 技能生成 `docs/superpowers/plans/2026-05-28-policy-revision-platform.md`  
3. 再进入实现（TDD / 私有化部署）
