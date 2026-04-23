# Legacy Analysis Scripts

以下脚本保留用于历史排查，不再作为主入口：

- `scripts/analyze_shenjian_themes_0407.py`
- `scripts/analyze_zhonganke_0410.py`
- `scripts/shenjian_simple_analysis.py`
- `scripts/quick_test.py`
- `scripts/check_shenjian_mainline.py`
- `scripts/test_correction.py`
- `scripts/test_fetch_features.py`
- `scripts/check_table_data.py`

统一入口：

```bash
.venv/bin/python scripts/analyze_stock_w2s.py --stock-code <CODE> --trade-date <YYYY-MM-DD>
```

示例：

```bash
.venv/bin/python scripts/analyze_stock_w2s.py --stock-code 002361 --trade-date 2026-04-07
.venv/bin/python scripts/analyze_stock_w2s.py --stock-code 605060 --trade-date 2026-04-15
```
