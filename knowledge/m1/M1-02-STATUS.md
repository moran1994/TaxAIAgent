# M1-02 切块导入说明

## 做了什么

1. **切块器** `apps/api/app/knowledge/chunker.py`  
   - 法规：按 `第×条`  
   - 公告：按 `一、二、…`  
   - 规则蒸馏标签（税率/留抵/进项等），**不改写正文**  
   - 忠实度：切块正文须为归一化原文子串  

2. **导入脚本** `apps/api/scripts/import_raw_corpus.py`  
   ```bash
   cd apps/api
   .venv/bin/python scripts/import_raw_corpus.py          # 全部 draft
   .venv/bin/python scripts/import_raw_corpus.py --publish # 忠实度通过则 published
   ```

3. **质检报告** `knowledge/m1/qa/chunk_import_report.{json,csv}`

## 本轮结果（2026-07-24）

| corpus | 策略 | 切块数 | 忠实度 |
|--------|------|--------|--------|
| C01 增值税法 | article | 38 | 38/38 |
| C02 实施条例 | article | 54 | 54/54 |
| C04 2019·39 | item | 9 | 9/9 |
| C05 留抵7号 | item | 11 | 11/11 |
| C06 留抵20号 | item | 14 | 14/14 |
| **合计** | | **126** | **126/126** |

已用 `--publish`：通过项均为 `published`。

## 禁止项自检

- [x] 无「模型回忆」法条入库  
- [x] citation body 为原文切块  
- [x] meta/source_url 来自官方  
- [x] 未用竞品库  

## 下一步

- M1-03 混合检索（对 published chunks）  
- 补下 C03/C07/C11 后再跑同一导入脚本  
- 专家抽检标签（≥30%）可在 CSV 上勾选
