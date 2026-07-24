# M1-01 知识对象 Schema

**状态**：已落入 `apps/api/app/models.py` 并随 API 启动建表  
**日期**：2026-07-24

## 实体

| 表 | 用途 | 关键字段 |
|----|------|----------|
| `policies` | 法规/公告文档 | `corpus_id`, `doc_no`, `source_url`, `tax_type`, 效力起止, `org_id?`, `raw_path` |
| `clauses` | 条款节点 | `clause_no`, `body`(**原文**), `status` draft/published/rejected, 蒸馏标签字段 |
| `chunks` | 检索切块 | `body` 原文子串, `embedding_ref`, `status` |
| `users` | 用户/专家 | `phone`, `role`, `enterprise_id?` |
| `conversations` / `messages` | 会话 | `citation_ids` |
| `tickets` | 专家工单 | 状态机 + `ticket_type`（预留 `risk_consult`） |
| `ledger_entries` | 分账 | 实付/手续费/专家/平台 |

## 查询能力

- 按 `tax_type`、效力、`status` 过滤条款（应用层）  
- `org_id` / `enterprise_id` 可空，供后续企业风险咨询挂载  

## 约束

- 发布态 `clauses.body` / `chunks.body` **不得**为模型改写摘要  
- 仅 `published` 进入检索索引（M1-03）
