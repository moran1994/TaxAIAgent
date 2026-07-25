# PRD Pack — 智能税务知识库问答助手

**流程**：prd · 已完成 draft → red_team → stories → compose  
**主题**：条款图谱可信问答 + 专家按单（咨询费分成）+ 后期挂载风险咨询

---

## 交付物索引

| 类型 | 路径 |
|------|------|
| PRD v0.1 | `prd/PRD-智能税务知识库问答助手.md` |
| 红队 | `prd/red-team-PRD-智能税务知识库问答助手.md` |
| 用户故事 P0 | `prd/user-stories-P0.md` |
| Sprint 排期 | `prd/sprint-plan.md` |
| Discovery Plan | `discovery/discovery-plan.md` |
| OST | `discovery/opportunity-solution-tree.md` |
| 假设 / 优先级 / 实验 | `discovery/assumptions-A-expert.md` 等 |
| 指标看板 | `discovery/metrics-dashboard.md` |
| 访谈脚本 | `discovery/interview-script.md` |

---

## 一句话范围

增值税等高频场景下：AI **强制引用**作答；不够确定则 **按单专家**书面答复；**用户咨询费与专家分成挂钩**。不做申报一体；企业风险咨询仅架构预留。

---

## 红队优先击杀（执行前必看）

1. WTP ∩ WTA 价带是否存在  
2. 纯问答是否为独立付费场景  
3. 图谱 10 题小样能否外推到质量门禁  
4. 「不确定」是否促转单  
5. 兼职专家 SLA/责任是否扛得住  

---

## P0 故事包摘要

| Epic | 故事 |
|------|------|
| A 可信问答 | A1–A5 提问、强制引用、原文、槽位、不确定态 |
| B 专家按单 | B1–B6 转专家、支付、工单、SLA、分账、评价退款 |
| C 门禁信任 | C1–C4 免责资质、入驻、黄金集、埋点 |
| D Concierge | D1–D2 Landing 假门、人工真单闭环 |

建议先 D+C2 → A 最小 → B 交易闭环。

---

## 建议下一步

1. 跑访谈脚本 + 10 题图谱小样（红队本周清单）  
2. Design 出答案卡 / 转专家 / 专家台线框  
3. 按 Sprint 切片进研发/Concierge  
4. （可选）再跑 pre-mortem 或拆 job-stories/WWAS  

---

*Compose artifact：`prd/prd-pack.md`*
