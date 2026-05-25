from pathlib import Path
from zipfile import ZipFile

import pytest

from wechat_complaint_tool.export_excel import (
    ExportComplaintData,
    build_export_row_from_text,
    collect_export_rows_from_run,
    find_latest_run_dir,
    list_record_images_for_excel,
)


def test_find_latest_run_dir_returns_newest_timestamp_dir(tmp_path: Path) -> None:
    older = tmp_path / "20260524_120000"
    newer = tmp_path / "20260524_130000"
    preview = tmp_path / "preview_20260524_235959"
    older.mkdir()
    newer.mkdir()
    preview.mkdir()

    assert find_latest_run_dir(tmp_path) == newer


def test_list_record_images_for_excel_reverses_order_and_skips_last_segment(tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    for name in ["001.png", "002.png", "003.png", "004.png"]:
        (complaint_dir / name).write_bytes(b"demo")

    images = list_record_images_for_excel(complaint_dir)

    assert [path.name for path in images] == ["003.png", "002.png", "001.png"]


def test_build_export_row_extracts_trade_ids_and_full_refund() -> None:
    text = """
    交易单号 4200003029202604283723348782
    商户单号 5921703241260428
    已发起退款    已退款至用户账户
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


def test_build_export_row_fallback_ignores_phone_number_for_merchant_order_id() -> None:
    text = """
    联系电话 19357345089
    5727532625260420
    """

    row = build_export_row_from_text(text)

    assert row.merchant_order_id == "5727532625260420"


def test_collect_export_rows_prefers_focus_text_for_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    (complaint_dir / "001.png").write_bytes(b"demo")

    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_directory_text",
        lambda complaint_dir, engine: "联系电话 19357345089\n已发起退款",
    )
    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_focus_text_from_directory",
        lambda complaint_dir, engine: "交易单号 4200003021202604200079355628\n商户单号 5727532625260420",
    )

    rows = collect_export_rows_from_run(tmp_path, ocr_engine=object())

    assert len(rows) == 1
    assert rows[0].transaction_id == "4200003021202604200079355628"
    assert rows[0].merchant_order_id == "5727532625260420"
    assert rows[0].refund_status == "全额退款（原路返回）"


def test_export_latest_run_to_workbook_writes_cell_images_format(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from PIL import Image

    from wechat_complaint_tool.export_excel import export_latest_run_to_workbook

    template = tmp_path / "template.xlsx"
    output_root = tmp_path / "output"
    run_dir = output_root / "20260524_155409"
    complaint_dir = run_dir / "0001_demo"
    complaint_dir.mkdir(parents=True)

    for name in ["001.png", "002.png", "003.png"]:
        Image.new("RGB", (60, 80), (255, 255, 255)).save(complaint_dir / name)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    workbook.save(template)

    result = export_latest_run_to_workbook(
        run_dir=run_dir,
        template_path=template,
        destination_dir=run_dir,
        rows=[
            ExportComplaintData(
                transaction_id="4200003029202604283723348782",
                merchant_order_id="5921703241260428",
                refund_summary="全额退款",
                refund_status="全额退款（原路返回）",
                complaint_dir=complaint_dir,
            )
        ],
    )

    loaded = openpyxl.load_workbook(result)
    sheet = loaded.active

    assert sheet["A2"].value == "4200003029202604283723348782"
    assert sheet["B2"].value == "5921703241260428"
    assert sheet["F2"].value == "全额退款（原路返回）"

    with ZipFile(result) as zf:
        names = set(zf.namelist())
        sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8", errors="replace")
        workbook_rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")

    assert "xl/cellimages.xml" in names
    assert "xl/_rels/cellimages.xml.rels" in names
    assert "xl/drawings/drawing1.xml" not in names
    assert '_xlfn.DISPIMG("ID_' in sheet_xml
    assert sheet_xml.count("_xlfn.DISPIMG(") == 2
    assert "officeDocument/2020/cellImage" in workbook_rels
