# M1-03 ~ M1-09 交付状态

**日期**：2026-07-25  
**范围**：混合检索 → 强制引用问答 → 对话 UI → 黄金集门禁 → 会话导出 → 简运营上下架

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/knowledge/search?q=` | 关键词 + char-ngram RRF 混合检索 |
| POST | `/v1/chat` | 强制引用问答（无命中→uncertain；拒答规则） |
| GET | `/v1/conversations/{id}/export` | 会话导出 |
| PATCH | `/v1/knowledge/clauses/{id}/status` | 上下架 + 审计 |
| GET | `/v1/knowledge/audit` | 审计列表 |
| GET | `/v1/meta/prompt` | Prompt 版本 |

## 本地命令

```bash
cd apps/api
.venv/bin/python scripts/import_raw_corpus.py --publish
.venv/bin/python scripts/eval_golden.py
uvicorn app.main:app --reload --port 8000
```

前端：`cd apps/web && npm i && npm run dev`

## 评测（种子 8 题）

见 `knowledge/m1/qa/golden_eval_report.json`：  
`retrieval_hit_rate=1.0`，`hard_hallucination_rate=0.0`，`gate_ok=true`。

完整 50 题需专家回填 `clause_ref` 后再扩。

## 技术说明

- 未配置 `LLM_API_KEY` 时走**摘录式回退**，仍绑定 `citation_ids`，禁止无引用确定性结论。  
- 「向量」侧为 char-ngram 余弦，可后续替换为真实 embedding 而不改 API。  
- Prompt：`ops/prompts/vat_qa_v1.json`。
