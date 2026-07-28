# M0 执行清单

| ID | 项 | 文档/代码 | 状态 |
|----|----|-----------|------|
| M0-01 | 语料+50题 | `knowledge/m0/` | 文档完成 · 待专家改定 clause_ref |
| M0-02 | 免责拒答 | `ops/m0/disclaimer-and-refusal.md` | 文档完成 · 待法务/产品签字 |
| M0-03 | 专家冷启动 | `ops/m0/expert-recruitment.md` | 材料完成 · 待真人意向≥5 |
| M0-04 | 脚手架 | `apps/api` `apps/web` `README.md` | 代码完成 |
| **S0** | **验证闸门落地包** | **`ops/s0/`** | **Runbook/假门/话术/10题/追踪/GoNoGo 已齐 · 待开跑** |
| M1-01 | Schema | `apps/api/app/models.py` `knowledge/m1/schema.md` | 已建表模型 |
| M1-02 | 切块入库 | `scripts/import_raw_corpus.py` + `knowledge/m1/qa/` | **126 切块全部忠实度通过并 published** |

**下一任务**：M1-02 原文落库 + 蒸馏辅助切块（先下载 C05/C06 等 P0 原文到 `knowledge/raw/`）。
