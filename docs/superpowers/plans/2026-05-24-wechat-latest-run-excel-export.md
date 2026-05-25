# 微信投诉最新采集结果导出 Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有微信投诉采集工具上新增“按最新一次采集目录自动生成表格”的能力，复用固定 Excel 模板，提取交易单号、商户单号、退款情况，并按倒序插入沟通记录截图。

**Architecture:** 保持现有采集链路不变，在批量采集完成后追加一个独立的“表格导出”阶段。新建专门的导出模块负责定位最新采集目录、解析每个投诉目录中的截图、生成基于模板的 Excel 副本，并将结果路径返回 GUI 展示；同时保留一个手动触发“仅按最新采集结果生成表格”的入口，便于补跑。

**Tech Stack:** Python 3.14, openpyxl, Pillow, tkinter, pytest

---

## File Structure

- Create: `app/wechat_complaint_tool/export_excel.py`
  - 负责最新采集目录定位、截图 OCR 文本提取、退款状态判断、模板复制和 Excel 图片插入。
- Modify: `app/wechat_complaint_tool/config.py`
  - 增加固定模板目录与表格输出目录的默认解析配置。
- Modify: `app/wechat_complaint_tool/gui.py`
  - 新增表格输出路径展示、手动“仅生成表格”按钮，并在批量采集完成后自动触发表格生成。
- Modify: `app/wechat_complaint_tool/automation.py`
  - 让批量运行结果返回的信息可供后续导出模块直接使用。
- Create: `tests/test_export_excel.py`
  - 覆盖最新采集目录定位、字段提取、截图倒序插入规则、模板导出结果。
- Modify: `README.md`
  - 更新新增表格导出能力和使用方式。

### Task 1: Add failing tests for latest-run directory discovery and segment ordering

**Files:**
- Create: `tests/test_export_excel.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from wechat_complaint_tool.export_excel import find_latest_run_dir, list_record_images_for_excel


def test_find_latest_run_dir_returns_newest_timestamp_dir(tmp_path: Path) -> None:
    older = tmp_path / "20260524_120000"
    newer = tmp_path / "20260524_130000"
    older.mkdir()
    newer.mkdir()

    assert find_latest_run_dir(tmp_path) == newer


def test_list_record_images_for_excel_reverses_order_and_skips_last_segment(tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    for name in ["001.png", "002.png", "003.png", "004.png"]:
        (complaint_dir / name).write_bytes(b"demo")

    images = list_record_images_for_excel(complaint_dir)

    assert [path.name for path in images] == ["003.png", "002.png", "001.png"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k "latest_run_dir or list_record_images"`
Expected: FAIL with `ModuleNotFoundError: No module named 'wechat_complaint_tool.export_excel'`

- [ ] **Step 3: Write minimal implementation**

```python
from pathlib import Path


def find_latest_run_dir(root: Path) -> Path:
    run_dirs = [path for path in root.iterdir() if path.is_dir()]
    if not run_dirs:
        raise FileNotFoundError("No capture run directories found")
    return max(run_dirs, key=lambda path: path.name)


def list_record_images_for_excel(complaint_dir: Path) -> list[Path]:
    images = sorted(complaint_dir.glob("*.png"))
    if len(images) <= 1:
        return []
    return list(reversed(images[:-1]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k "latest_run_dir or list_record_images"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_excel.py app/wechat_complaint_tool/export_excel.py
git commit -m "test: add latest-run export scaffolding"
```

### Task 2: Add failing tests for screenshot text extraction and refund result normalization

**Files:**
- Modify: `tests/test_export_excel.py`

- [ ] **Step 1: Write the failing tests**

```python
from wechat_complaint_tool.export_excel import ExportComplaintData, build_export_row_from_text


def test_build_export_row_extracts_trade_ids_and_full_refund() -> None:
    text = """
    交易单号 4200003029202604283723348782
    商户单号 5921703241260428
    已发起退款
    已退款至用户账户
    已发起全额退款
    """

    row = build_export_row_from_text(text)

    assert row.transaction_id == "4200003029202604283723348782"
    assert row.merchant_order_id == "5921703241260428"
    assert row.refund_status == "全额退款（原路返回）"


def test_build_export_row_defaults_to_unrefunded_when_refund_text_missing() -> None:
    text = """
    交易单号 4200003105202605212997778600
    商户单号 5555275103260521
    用户提交问题咨询
    """

    row = build_export_row_from_text(text)

    assert row.refund_status == "未退款"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k "build_export_row"`
Expected: FAIL with `ImportError` or assertion failure for missing parser

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
import re


@dataclass(slots=True)
class ExportComplaintData:
    transaction_id: str
    merchant_order_id: str
    refund_status: str


def build_export_row_from_text(text: str) -> ExportComplaintData:
    transaction_id = _extract_long_number(text, "交易单号")
    merchant_order_id = _extract_long_number(text, "商户单号")
    refund_status = "全额退款（原路返回）" if "全额退款" in text or "已退款至用户账户" in text else "未退款"
    return ExportComplaintData(transaction_id=transaction_id, merchant_order_id=merchant_order_id, refund_status=refund_status)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k "build_export_row"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_excel.py app/wechat_complaint_tool/export_excel.py
git commit -m "test: cover export field extraction"
```

### Task 3: Add failing tests for template workbook generation and image insertion

**Files:**
- Modify: `tests/test_export_excel.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from wechat_complaint_tool.export_excel import ExportComplaintData, export_latest_run_to_workbook


def test_export_latest_run_to_workbook_writes_ids_refund_and_images(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    output_root = tmp_path / "output"
    run_dir = output_root / "20260524_155409"
    complaint_dir = run_dir / "0001_demo"
    complaint_dir.mkdir(parents=True)

    for name in ["001.png", "002.png", "003.png"]:
        Image.new("RGB", (60, 80), (255, 255, 255)).save(complaint_dir / name)

    _build_template_workbook(template)

    result = export_latest_run_to_workbook(
        run_dir=run_dir,
        template_path=template,
        destination_dir=run_dir,
        rows=[
            ExportComplaintData(
                transaction_id="4200003029202604283723348782",
                merchant_order_id="5921703241260428",
                refund_status="全额退款（原路返回）",
                complaint_dir=complaint_dir,
            )
        ],
    )

    workbook = load_workbook(result)
    sheet = workbook.active

    assert sheet["A2"].value == "4200003029202604283723348782"
    assert sheet["B2"].value == "5921703241260428"
    assert sheet["F2"].value == "全额退款（原路返回）"
    assert len(sheet._images) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k export_latest_run_to_workbook`
Expected: FAIL with missing workbook export implementation

- [ ] **Step 3: Write minimal implementation**

```python
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage


def export_latest_run_to_workbook(...):
    workbook = load_workbook(template_path)
    sheet = workbook.active
    for index, row in enumerate(rows, start=2):
        sheet[f"A{index}"] = row.transaction_id
        sheet[f"B{index}"] = row.merchant_order_id
        sheet[f"F{index}"] = row.refund_status
        for column, image_path in zip(["I", "J", "K", "L"], list_record_images_for_excel(row.complaint_dir)):
            sheet.add_image(XLImage(str(image_path)), f"{column}{index}")
    output_path = destination_dir / f"{run_dir.name}_处理表格.xlsx"
    workbook.save(output_path)
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py -k export_latest_run_to_workbook`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_export_excel.py app/wechat_complaint_tool/export_excel.py
git commit -m "feat: export complaint workbook from latest run"
```

### Task 4: Install dependency and wire OCR-driven export orchestration

**Files:**
- Modify: `app/wechat_complaint_tool/export_excel.py`

- [ ] **Step 1: Install dependency**

Run: `py -3.14 -m pip install openpyxl`
Expected: installation succeeds and `openpyxl` import works

- [ ] **Step 2: Expand orchestration to use OCR on the kept screenshots**

```python
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def collect_export_rows_from_run(run_dir: Path, ocr_engine: RapidOCR | None = None) -> list[ExportComplaintData]:
    engine = ocr_engine or RapidOCR()
    rows = []
    for complaint_dir in _iter_complaint_dirs(run_dir):
        images = sorted(complaint_dir.glob("*.png"))
        text = "\n".join(_ocr_image(engine, image_path) for image_path in images)
        row = build_export_row_from_text(text)
        row.complaint_dir = complaint_dir
        rows.append(row)
    return rows
```

- [ ] **Step 3: Run tests for export module**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/wechat_complaint_tool/export_excel.py tests/test_export_excel.py
git commit -m "feat: add OCR-driven workbook export pipeline"
```

### Task 5: Integrate automatic export after batch and manual latest-run export in GUI

**Files:**
- Modify: `app/wechat_complaint_tool/gui.py`
- Modify: `app/wechat_complaint_tool/config.py`

- [ ] **Step 1: Write failing GUI-adjacent tests or targeted assertions**

```python
def test_build_config_keeps_default_output_dir_for_excel():
    config = AppConfig()
    assert config.output_dir == "image"
```

Add a focused test if GUI unit coverage is practical; otherwise keep logic in helper functions in `export_excel.py` and test there.

- [ ] **Step 2: Modify config and GUI to show workbook output path and manual export button**

```python
self.excel_output_var = tk.StringVar(value="未生成")
ttk.Button(buttons, text="按最新采集结果生成表格", command=self._export_latest_run).grid(...)
ttk.Label(status_frame, textvariable=self.excel_output_var, justify="left").grid(...)
```

- [ ] **Step 3: Trigger export automatically after batch completes**

```python
manifest_path = self.runner.run(callbacks)
excel_path = export_latest_run_with_fixed_template(
    base_dir=self.base_dir,
    output_root=self._resolve_output_dir(),
)
self.root.after(0, lambda: self.excel_output_var.set(str(excel_path)))
```

- [ ] **Step 4: Run targeted tests**

Run: `py -3.14 -m pytest -q tests/test_export_excel.py tests/test_config.py tests/test_automation.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/wechat_complaint_tool/gui.py app/wechat_complaint_tool/config.py app/wechat_complaint_tool/export_excel.py tests/test_export_excel.py
git commit -m "feat: auto-export latest capture run to workbook"
```

### Task 6: Update docs and verify end-to-end behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README usage and output structure**

```markdown
- 批量采集完成后会自动基于最新一次采集目录生成 Excel
- 也可点击“按最新采集结果生成表格”单独补跑
- 生成结果位于采集运行目录下，例如 `image/20260524_155409/20260524_155409_处理表格.xlsx`
```

- [ ] **Step 2: Run full verification**

Run: `py -3.14 -m pytest -q`
Expected: all tests pass

- [ ] **Step 3: Run import smoke check**

Run:

```powershell
@'
import sys
sys.path.insert(0, 'app')
import wechat_complaint_tool.export_excel
import wechat_complaint_tool.gui
print('import-ok')
'@ | py -3.14 -
```

Expected: `import-ok`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe workbook export flow"
```

## Self-Review

- Spec coverage:
  - 固定模板路径：Task 4/5 里通过固定模板辅助函数接入。
  - 默认最新采集目录：Task 1/4/5 覆盖。
  - 自动生成与手动补跑：Task 5 覆盖。
  - 字段提取与退款状态：Task 2/4 覆盖。
  - 图片倒序插入且跳过最后一张：Task 1/3 覆盖。
- Placeholder scan:
  - 没有 `TODO/TBD`。
  - 每个任务包含明确文件、命令和最小代码骨架。
- Type consistency:
  - `ExportComplaintData`、`find_latest_run_dir`、`list_record_images_for_excel`、`export_latest_run_to_workbook` 在任务中命名一致。
