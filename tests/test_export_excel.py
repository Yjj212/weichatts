from pathlib import Path
from zipfile import ZipFile

import pytest

from wechat_complaint_tool.export_excel import (
    ExportComplaintData,
    _ocr_focus_text_from_directory,
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


def test_list_record_images_for_excel_excludes_order_info_png(tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    for name in ["001.png", "002.png", "003.png", "order_info.png"]:
        (complaint_dir / name).write_bytes(b"demo")

    images = list_record_images_for_excel(complaint_dir)

    assert [path.name for path in images] == ["002.png", "001.png"]


def test_ocr_focus_text_from_directory_prefers_order_info_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    for name in ["001.png", "002.png", "order_info.png"]:
        (complaint_dir / name).write_bytes(b"demo")

    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_focus_text_from_image",
        lambda image_path, engine: image_path.name,
    )

    text = _ocr_focus_text_from_directory(complaint_dir, engine=object())

    assert text == "order_info.png"


def test_build_export_row_extracts_trade_ids_full_refund_and_new_fields() -> None:
    text = """
    交易单号 4200003029202604283723348782
    商户单号 5921703241260428
    交易金额 ¥68.00
    交易时间 2026/04/20 21:46:46
    咨询时间 2026/04/20 21:56:39
    问题描述 支付点错了，开年费，点成月费了
    已发起退款 已退款至用户账户
    已发起全额退款
    """

    row = build_export_row_from_text(text)

    assert row.transaction_id == "4200003029202604283723348782"
    assert row.merchant_order_id == "5921703241260428"
    assert row.transaction_amount == "68.00"
    assert row.transaction_time == "2026/04/20 21:46:46"
    assert row.inquiry_time == "2026/04/20 21:56:39"
    assert row.problem_description == "支付点错了，开年费，点成月费了"
    assert row.refund_status == "全额退款（原路返回）"


def test_build_export_row_extracts_amount_and_consult_reason_from_realistic_focus_text() -> None:
    text = """
    用户提交问题咨询
    交易商品
    上网服务-客服电话4006211990
    交易金额
    ¥68.00
    交易时间
    2026/04/20 21:46:46
    交易单号
    4200003021202604200079355628
    商户单号
    5727532625260420
    咨询原因
    其他问题
    咨询时间
    2026/04/20 21:56:39
    """

    row = build_export_row_from_text(text)

    assert row.transaction_amount == "68.00"
    assert row.problem_description == "其他问题"


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


def test_collect_export_rows_prefers_focus_text_for_ids_and_extra_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    (complaint_dir / "001.png").write_bytes(b"demo")

    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_directory_text",
        lambda complaint_dir, engine: "联系电话 19357345089\n已发起退款",
    )
    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_focus_text_from_directory",
        lambda complaint_dir, engine: (
            "交易单号 4200003021202604200079355628\n"
            "商户单号 5727532625260420\n"
            "交易金额 ¥68.00\n"
            "交易时间 2026/04/20 21:46:46\n"
            "咨询时间 2026/04/20 21:56:39\n"
            "问题描述 支付点错了，开年费，点成月费了"
        ),
    )

    rows = collect_export_rows_from_run(tmp_path, ocr_engine=object())

    assert len(rows) == 1
    assert rows[0].transaction_id == "4200003021202604200079355628"
    assert rows[0].merchant_order_id == "5727532625260420"
    assert rows[0].transaction_amount == "68.00"
    assert rows[0].transaction_time == "2026/04/20 21:46:46"
    assert rows[0].inquiry_time == "2026/04/20 21:56:39"
    assert rows[0].problem_description == "支付点错了，开年费，点成月费了"
    assert rows[0].refund_status == "全额退款（原路返回）"


def test_collect_export_rows_keeps_best_available_values_when_focus_text_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    complaint_dir = tmp_path / "0001_demo"
    complaint_dir.mkdir()
    (complaint_dir / "001.png").write_bytes(b"demo")

    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_directory_text",
        lambda complaint_dir, engine: (
            "商户单号 5591845407260415\n"
            "咨询时间 2026/04/15 21:08:29\n"
            "问题描述 退款充值不了会员，请退款\n"
            "交易金额 ￥59.98\n"
            "交易时间 2026/04/15 21:05:25"
        ),
    )
    monkeypatch.setattr(
        "wechat_complaint_tool.export_excel._ocr_focus_text_from_directory",
        lambda complaint_dir, engine: "用户提交问题咨询\n交易商品\n上网服务-客服电话4006211990",
    )

    rows = collect_export_rows_from_run(tmp_path, ocr_engine=object())

    assert len(rows) == 1
    assert rows[0].transaction_id == ""
    assert rows[0].merchant_order_id == "5591845407260415"
    assert rows[0].transaction_amount == "59.98"
    assert rows[0].transaction_time == "2026/04/15 21:05:25"
    assert rows[0].inquiry_time == "2026/04/15 21:08:29"
    assert rows[0].problem_description == "退款充值不了会员，请退款"


def test_export_latest_run_to_workbook_writes_cell_images_format_and_new_columns(tmp_path: Path) -> None:
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
                transaction_amount="68.00",
                transaction_time="2026/04/20 21:46:46",
                inquiry_time="2026/04/20 21:56:39",
                problem_description="支付点错了，开年费，点成月费了",
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
    assert sheet["C2"].value == "68.00"
    assert sheet["D2"].value == "2026/04/20 21:46:46"
    assert sheet["E2"].value == "2026/04/20 21:56:39"
    assert sheet["F2"].value == "支付点错了，开年费，点成月费了"
    assert sheet["G2"].value == "全额退款"
    assert sheet["J2"].value == "全额退款（原路返回）"

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
