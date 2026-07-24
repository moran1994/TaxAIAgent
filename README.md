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

见 `.env.example`。`OPENAI_API_KEY` / 国内大模型 Key **不要提交到 Git**。

## 知识库原则

权威原文为唯一真源；LLM 蒸馏仅辅助打标；禁止无原文入库。详见 backlog `M1-02`。
