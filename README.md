# 条款问税 · TaxAIAgent

增值税窄域 **强制引用 RAG** + **专家按单分成** Concierge MVP。

## 文档

| 路径 | 说明 |
|------|------|
| `prd/PRD-tax-kb-mvp.md` | MVP PRD |
| `prd/backlog-mvp-tasks.md` | 开发任务 |
| `knowledge/m0/` | 语料清单与黄金集 |
| `ops/m0/` | 免责、拒答、专家招募 |
| `discovery/` | 发现阶段产出 |

## 本地启动

### 后端 API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env   # 如尚未创建
uvicorn app.main:app --reload --port 8000
```

健康检查：http://localhost:8000/health  
API 文档：http://localhost:8000/docs

### 前端

```bash
cd apps/web
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认 http://localhost:5173）。

## 环境变量

见 `.env.example`。`LLM_API_KEY` / 微信商户密钥 **不要提交到 Git**。

- `PAYMENT_PROVIDER=mock`（默认）或 `wechat`（需配置 `WECHAT_MCH_ID` 等；当前为 stub）
- `EXPERT_RATIO=0.70` 分账专家占比

## 知识库原则

权威原文为唯一真源；LLM 蒸馏仅辅助打标；禁止无原文入库。详见 backlog `M1-02`。

已入库 P0：`C01`/`C02`/`C03a`–`C03e`/`C04`–`C07c`/`C11`（约 313 已发布切块）。

前端 Tab：用户问答（多轮）· 专家工作台 · 知识运营 · 指标。

## 常用命令

```bash
# 切块入库
cd apps/api && .venv/bin/python scripts/import_raw_corpus.py --publish

# 黄金集门禁（种子题）
.venv/bin/python scripts/eval_golden.py

# 问答（需 API 已启动）
curl -s http://127.0.0.1:8000/v1/knowledge/search?q=留抵退税 | head
curl -s -X POST http://127.0.0.1:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"query":"哪些进项不得抵扣"}'
```

进度：`knowledge/m1/M1-PROGRESS.md` · `knowledge/m1/M2-STATUS.md`

```bash
# M2 金路径
.venv/bin/python scripts/e2e_m2.py
```
