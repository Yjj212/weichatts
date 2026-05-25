from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .automation import AutomationCallbacks, BatchAutomationRunner
from .calibration import RegionSelector
from .capture import ScreenCaptureService, validate_capture_prerequisites
from .config import AppConfig, Rect, load_config, save_config
from .export_excel import export_latest_run_with_fixed_template
from .ocr_service import OCRService


class AppView:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config = load_config(base_dir)
        self.capture_service = ScreenCaptureService()
        self.ocr_service = OCRService()
        self.runner: BatchAutomationRunner | None = None

        self.root = tk.Tk()
        self.root.title("微信投诉分段截图助手")
        self.root.geometry("900x700")

        self.window_title_var = tk.StringVar(value=self.config.window_title_hint)
        self.output_dir_var = tk.StringVar(value=self.config.output_dir)
        self.scroll_delay_var = tk.StringVar(value=str(self.config.scroll_settle_ms))
        self.chat_scroll_clicks_var = tk.StringVar(value=str(self.config.chat_scroll_clicks))
        self.page_ratio_var = tk.StringVar(value=str(self.config.list_page_scroll_ratio))
        self.overlap_var = tk.StringVar(value=str(self.config.capture_overlap_threshold))
        self.status_var = tk.StringVar(value="准备就绪")
        self.progress_var = tk.StringVar(value="已完成 0，失败 0")
        self.current_item_var = tk.StringVar(value="当前投诉：无")
        self.excel_output_var = tk.StringVar(value="表格输出：未生成")

        self.window_region_var = tk.StringVar(value=self._format_rect(self.config.wechat_window_rect))
        self.list_region_var = tk.StringVar(value=self._format_rect(self.config.list_region))
        self.content_region_var = tk.StringVar(value=self._format_rect(self.config.content_region))

        self._build_layout()
        self._set_status("请先点击“设置区域”，依次框选微信窗口、左侧列表和右侧完整内容区域。")

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="微信窗口标题关键字").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.window_title_var).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="输出目录").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(frame, text="选择目录", command=self._pick_output_dir).grid(row=1, column=2, padx=(8, 0))

        settings = ttk.LabelFrame(frame, text="运行参数", padding=12)
        settings.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for column in range(4):
            settings.columnconfigure(column, weight=1)

        ttk.Label(settings, text="滚动等待毫秒").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.scroll_delay_var).grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Label(settings, text="右侧滚动步长").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.chat_scroll_clicks_var).grid(row=0, column=3, sticky="ew")

        ttk.Label(settings, text="左侧翻页比例").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.page_ratio_var).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(10, 0))
        ttk.Label(settings, text="重复裁剪阈值").grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Entry(settings, textvariable=self.overlap_var).grid(row=1, column=3, sticky="ew", pady=(10, 0))

        region_frame = ttk.LabelFrame(frame, text="区域信息", padding=12)
        region_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        region_frame.columnconfigure(1, weight=1)
        self._add_region_row(region_frame, 0, "微信窗口", self.window_region_var)
        self._add_region_row(region_frame, 1, "左侧投诉列表", self.list_region_var)
        self._add_region_row(region_frame, 2, "右侧完整内容", self.content_region_var)

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for column in range(6):
            buttons.columnconfigure(column, weight=1)

        ttk.Button(buttons, text="设置区域", command=self._setup_regions).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Button(buttons, text="保存配置", command=self._save_form).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(buttons, text="预览当前投诉分段图", command=self._preview_current).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(buttons, text="开始批量采集", command=self._start_batch).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(buttons, text="暂停/继续", command=self._toggle_pause).grid(row=0, column=4, sticky="ew", padx=4)
        ttk.Button(buttons, text="按最新采集结果生成表格", command=self._export_latest_run).grid(row=0, column=5, sticky="ew", padx=4)

        stop_row = ttk.Frame(frame)
        stop_row.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        stop_row.columnconfigure(0, weight=1)
        stop_row.rowconfigure(1, weight=1)
        ttk.Button(stop_row, text="停止本次采集", command=self._stop_batch).grid(row=0, column=0, sticky="ew")

        status_frame = ttk.LabelFrame(stop_row, text="状态", padding=12)
        status_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        status_frame.columnconfigure(0, weight=1)

        ttk.Label(status_frame, textvariable=self.progress_var, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self.current_item_var, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.excel_output_var, justify="left", wraplength=820).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.status_var, justify="left", wraplength=820).grid(row=3, column=0, sticky="nw", pady=(6, 0))

    def _add_region_row(self, parent: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Label(parent, textvariable=variable).grid(row=row, column=1, sticky="w", pady=4)

    def _setup_regions(self) -> None:
        self.root.withdraw()
        self.root.update_idletasks()
        selector = RegionSelector(self.root)
        try:
            window_rect = selector.select_rect("框选微信窗口")
            if window_rect is None:
                return
            list_rect = selector.select_rect("框选左侧投诉列表区域")
            if list_rect is None:
                return
            content_rect = selector.select_rect("框选右侧完整内容区域")
            if content_rect is None:
                return
        finally:
            self.root.deiconify()
            self.root.lift()

        self.config = replace(
            self.config,
            wechat_window_rect=window_rect,
            list_region=list_rect,
            content_region=content_rect,
        )
        self._refresh_region_labels()
        self._set_status("区域设置完成，请先保存配置并预览一次分段截图。")

    def _preview_current(self) -> None:
        self._save_form()
        issues = validate_capture_prerequisites(self.config)
        if issues:
            messagebox.showwarning("无法预览", "\n".join(issues))
            return

        output_dir = self._resolve_output_dir()
        preview_dir = output_dir / f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def worker() -> None:
            try:
                result = self.capture_service.capture_current_complaint_segments(self.config, preview_dir)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: messagebox.showerror("预览失败", str(exc)))
                self.root.after(0, lambda: self._set_status(f"预览失败：{exc}"))
                return

            self.root.after(0, lambda: self._set_status(f"预览分段图已保存，共 {result.segment_count} 张：{result.output_dir}"))
            self.root.after(
                0,
                lambda: messagebox.showinfo("预览完成", f"已保存到：\n{result.output_dir}\n共 {result.segment_count} 张图片"),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _start_batch(self) -> None:
        self._save_form()
        issues = validate_capture_prerequisites(self.config)
        if issues:
            messagebox.showwarning("无法开始", "\n".join(issues))
            return

        self.runner = BatchAutomationRunner(self.config, self.capture_service, self.ocr_service, self.base_dir)
        callbacks = AutomationCallbacks(on_status=self._queue_status, on_progress=self._queue_progress)

        def worker() -> None:
            try:
                manifest_path = self.runner.run(callbacks)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: messagebox.showerror("采集失败", str(exc)))
                self.root.after(0, lambda: self._set_status(f"采集失败：{exc}"))
                return

            try:
                excel_path = export_latest_run_with_fixed_template(self.base_dir, self._resolve_output_dir(), ocr_engine=self.ocr_service.engine)
                self.root.after(0, lambda: self.excel_output_var.set(f"表格输出：{excel_path}"))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self.excel_output_var.set(f"表格输出失败：{exc}"))

            self.root.after(0, lambda: self._set_status(f"批量采集完成，结果清单：{manifest_path}"))
            self.root.after(0, lambda: messagebox.showinfo("采集完成", f"结果清单已生成：\n{manifest_path}"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("批量采集已启动，请不要操作微信窗口。")

    def _export_latest_run(self) -> None:
        self._save_form()

        def worker() -> None:
            try:
                excel_path = export_latest_run_with_fixed_template(self.base_dir, self._resolve_output_dir(), ocr_engine=self.ocr_service.engine)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: messagebox.showerror("生成表格失败", str(exc)))
                self.root.after(0, lambda: self._set_status(f"生成表格失败：{exc}"))
                return

            self.root.after(0, lambda: self.excel_output_var.set(f"表格输出：{excel_path}"))
            self.root.after(0, lambda: self._set_status(f"表格已生成：{excel_path}"))
            self.root.after(0, lambda: messagebox.showinfo("生成完成", f"已生成表格：\n{excel_path}"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("正在根据最新采集结果生成表格。")

    def _toggle_pause(self) -> None:
        if self.runner is None:
            messagebox.showinfo("提示", "当前没有正在运行的采集任务。")
            return
        if self.runner._pause_event.is_set():
            self.runner.pause()
            self._set_status("已暂停。再次点击可继续。")
        else:
            self.runner.resume()
            self._set_status("已继续采集。")

    def _stop_batch(self) -> None:
        if self.runner is None:
            return
        self.runner.stop()
        self._set_status("已请求停止，本轮会在安全位置结束。")

    def _pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.base_dir))
        if selected:
            self.output_dir_var.set(selected)

    def _save_form(self) -> None:
        try:
            self.config = self._build_config_from_form()
        except ValueError as exc:
            messagebox.showerror("保存失败", str(exc))
            raise
        save_config(self.base_dir, self.config)
        self._refresh_region_labels()
        self._set_status("配置已保存。")

    def _build_config_from_form(self) -> AppConfig:
        scroll_settle_ms = int(self.scroll_delay_var.get())
        chat_scroll_clicks = int(self.chat_scroll_clicks_var.get())
        page_ratio = float(self.page_ratio_var.get())
        overlap = float(self.overlap_var.get())

        if scroll_settle_ms < 0:
            raise ValueError("滚动等待毫秒不能小于 0")
        if not (1 <= chat_scroll_clicks <= 12):
            raise ValueError("右侧滚动步长建议在 1 到 12 之间")
        if not (0.1 <= page_ratio <= 2.0):
            raise ValueError("左侧翻页比例建议在 0.1 到 2.0 之间")
        if not (0.5 <= overlap <= 1.0):
            raise ValueError("重复裁剪阈值必须在 0.5 到 1.0 之间")

        return replace(
            self.config,
            window_title_hint=self.window_title_var.get().strip() or "微信",
            output_dir=self.output_dir_var.get().strip() or "image",
            scroll_settle_ms=scroll_settle_ms,
            chat_scroll_clicks=chat_scroll_clicks,
            list_page_scroll_ratio=page_ratio,
            capture_overlap_threshold=overlap,
        )

    def _resolve_output_dir(self) -> Path:
        configured = Path(self.output_dir_var.get().strip() or "image")
        if configured.is_absolute():
            return configured
        return self.base_dir / configured

    def _refresh_region_labels(self) -> None:
        self.window_region_var.set(self._format_rect(self.config.wechat_window_rect))
        self.list_region_var.set(self._format_rect(self.config.list_region))
        self.content_region_var.set(self._format_rect(self.config.content_region))

    @staticmethod
    def _format_rect(rect: Rect | None) -> str:
        if rect is None:
            return "未设置"
        return f"left={rect.left}, top={rect.top}, width={rect.width}, height={rect.height}"

    def _queue_status(self, message: str) -> None:
        self.root.after(0, lambda: self._set_status(message))

    def _queue_progress(self, completed: int, failed: int, display_name: str, amount_text: str) -> None:
        self.root.after(0, lambda: self.progress_var.set(f"已完成 {completed}，失败 {failed}"))
        self.root.after(0, lambda: self.current_item_var.set(f"当前投诉：{display_name} {amount_text}".strip()))

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
