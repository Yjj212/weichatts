from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

from .config import Rect


@dataclass(slots=True)
class RegionSelector:
    root: tk.Tk

    def select_rect(self, title: str) -> Rect | None:
        result: dict[str, Rect | None] = {"rect": None}
        overlay = tk.Toplevel(self.root)
        overlay.title(title)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.25)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")
        overlay.focus_force()

        canvas = tk.Canvas(overlay, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)

        start: tuple[int, int] | None = None
        rect_id: int | None = None

        def on_press(event: tk.Event) -> None:
            nonlocal start, rect_id
            start = (event.x_root, event.y_root)
            rect_id = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#44ff88", width=2)

        def on_drag(event: tk.Event) -> None:
            if start is None or rect_id is None:
                return
            x0, y0 = start
            canvas.coords(rect_id, x0, y0, event.x_root, event.y_root)

        def on_release(event: tk.Event) -> None:
            if start is None:
                return
            x0, y0 = start
            x1, y1 = event.x_root, event.y_root
            left = min(x0, x1)
            top = min(y0, y1)
            width = abs(x1 - x0)
            height = abs(y1 - y0)
            result["rect"] = None if width == 0 or height == 0 else Rect(left, top, width, height)
            overlay.destroy()

        overlay.bind("<Escape>", lambda _event: overlay.destroy())
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.wait_window()
        return result["rect"]
