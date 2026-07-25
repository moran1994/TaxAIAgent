# M2 / M3 最小交付

## M2 已实现

| ID | 能力 | 入口 |
|----|------|------|
| M2-01 | 两档报价下单 + 会话上下文摘要 | `POST /v1/tickets` |
| M2-02 | **模拟微信支付**沙箱 | `POST /v1/tickets/{id}/pay/mock` |
| M2-03 | 状态机 + SLA 24h | `app/services/tickets.py` |
| M2-04 | 专家待接池/领单/答复（demo 专家） | `/v1/expert/*` + Web「专家工作台」 |
| M2-05 | 完成自动分账 + CSV | `GET /v1/ledger.csv` |
| M2-06 | 评价 + 退款申请/审批 | `/rate` `/refund/*` |
| M2-07 | E2E 脚本 | `scripts/e2e_m2.py` |

## M3 最小

| ID | 能力 |
|----|------|
| M3-01 | `GET /v1/metrics/kr` |
| M3-02 | Web 首页即获客入口（品牌+提问 CTA） |
| M3-03 | `ops/m3/retro-template.md` 周复盘模板 |

## 验证

```bash
cd apps/api
.venv/bin/python scripts/import_raw_corpus.py --publish   # 若库空
.venv/bin/python scripts/e2e_m2.py
```

真实微信/支付宝尚未接入；Concierge 期用 mock 验闭环。
