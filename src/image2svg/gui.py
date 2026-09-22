from __future__ import annotations

import contextlib
import io
import os
import queue
import subprocess
import threading
from pathlib import Path

from image2svg.cli import main as cli_main

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
PRESET_LABELS = {
    "基础模式（仅 SVG）": None,
    "平衡模式（推荐）": "balanced",
    "论文与复杂图增强": "paper",
}


def build_cli_arguments(
    input_path: Path,
    output_dir: Path,
    preset: str | None,
    *,
    qa: bool = True,
    review_html: bool = True,
    arrows: bool = False,
    ai_python: str | None = None,
    model_root: str | None = None,
    output_stem: str | None = None,
) -> list[str]:
    stem = output_stem or input_path.stem
    arguments = [
        str(input_path),
        "-o",
        str(output_dir / f"{stem}.svg"),
        "--pptx",
        str(output_dir / f"{stem}.pptx"),
    ]
    if review_html:
        arguments.extend(["--html", str(output_dir / f"{stem}.review.html")])
    if preset:
        arguments.extend(["--preset", preset])
    if qa or review_html:
        arguments.append("--qa")
    if arrows:
        arguments.append("--arrows")
    if ai_python:
        arguments.extend(["--ai-python", ai_python])
    if model_root:
        arguments.extend(["--model-root", model_root])
    return arguments


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tkinter is required to run image2svg-gui") from exc

    root = tk.Tk()
    root.title("image2svg")
    root.geometry("900x680")
    root.minsize(760, 560)

    files: list[Path] = []
    events: queue.Queue[tuple[str, str]] = queue.Queue()
    running = tk.BooleanVar(value=False)
    output_var = tk.StringVar(value=str(Path.cwd() / "output"))
    preset_var = tk.StringVar(value="平衡模式（推荐）")
    ai_python_var = tk.StringVar(value=os.environ.get("IMAGE2SVG_AI_PYTHON", ""))
    model_root_var = tk.StringVar(value=os.environ.get("IMAGE2SVG_MODEL_ROOT", ""))
    qa_var = tk.BooleanVar(value=True)
    review_var = tk.BooleanVar(value=True)
    arrows_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="请选择一个或多个图片")

    outer = ttk.Frame(root, padding=18)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)
    outer.rowconfigure(8, weight=1)

    ttk.Label(outer, text="图片转可编辑 SVG / PowerPoint", font=("Segoe UI", 18, "bold")).grid(
        row=0, column=0, sticky="w", pady=(0, 12)
    )

    file_buttons = ttk.Frame(outer)
    file_buttons.grid(row=1, column=0, sticky="ew", pady=(0, 6))
    file_buttons.columnconfigure(2, weight=1)

    file_list = tk.Listbox(outer, selectmode="extended", height=7)
    file_list.grid(row=2, column=0, sticky="nsew")

    def refresh_files() -> None:
        file_list.delete(0, tk.END)
        for item in files:
            file_list.insert(tk.END, str(item))

    def add_files() -> None:
        selected = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        for value in selected:
            path = Path(value)
            if path.suffix.lower() in SUPPORTED_IMAGES and path not in files:
                files.append(path)
        refresh_files()
        status_var.set(f"已选择 {len(files)} 张图片")

    def remove_files() -> None:
        selected = set(file_list.curselection())
        files[:] = [item for index, item in enumerate(files) if index not in selected]
        refresh_files()
        status_var.set(f"已选择 {len(files)} 张图片")

    ttk.Button(file_buttons, text="添加图片", command=add_files).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(file_buttons, text="移除选中", command=remove_files).grid(row=0, column=1)

    settings = ttk.LabelFrame(outer, text="转换设置", padding=12)
    settings.grid(row=3, column=0, sticky="ew", pady=12)
    settings.columnconfigure(1, weight=1)

    ttk.Label(settings, text="输出目录").grid(row=0, column=0, sticky="w", padx=(0, 10))
    ttk.Entry(settings, textvariable=output_var).grid(row=0, column=1, sticky="ew")

    def choose_output() -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            output_var.set(selected)

    ttk.Button(settings, text="浏览", command=choose_output).grid(row=0, column=2, padx=(8, 0))
    ttk.Label(settings, text="处理模式").grid(row=1, column=0, sticky="w", pady=(10, 0))
    ttk.Combobox(
        settings,
        textvariable=preset_var,
        values=list(PRESET_LABELS),
        state="readonly",
    ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 0))
    ttk.Label(settings, text="AI Python").grid(row=2, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(settings, textvariable=ai_python_var).grid(
        row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0)
    )
    ttk.Label(settings, text="模型根目录").grid(row=3, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(settings, textvariable=model_root_var).grid(
        row=3, column=1, columnspan=2, sticky="ew", pady=(10, 0)
    )

    checks = ttk.Frame(settings)
    checks.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
    ttk.Checkbutton(checks, text="生成 QA 对比", variable=qa_var).pack(side="left", padx=(0, 16))
    ttk.Checkbutton(checks, text="生成审阅 HTML", variable=review_var).pack(
        side="left", padx=(0, 16)
    )
    ttk.Checkbutton(checks, text="实验性箭头", variable=arrows_var).pack(side="left")

    progress = ttk.Progressbar(outer, mode="determinate")
    progress.grid(row=4, column=0, sticky="ew")
    ttk.Label(outer, textvariable=status_var).grid(row=5, column=0, sticky="w", pady=(6, 10))

    action_row = ttk.Frame(outer)
    action_row.grid(row=6, column=0, sticky="ew")
    action_row.columnconfigure(0, weight=1)
    start_button = ttk.Button(action_row, text="开始转换")
    start_button.grid(row=0, column=1)

    ttk.Label(outer, text="运行日志").grid(row=7, column=0, sticky="w", pady=(12, 4))
    log = tk.Text(outer, height=10, wrap="word", state="disabled")
    log.grid(row=8, column=0, sticky="nsew")

    def append_log(message: str) -> None:
        log.configure(state="normal")
        log.insert(tk.END, message.rstrip() + "\n")
        log.see(tk.END)
        log.configure(state="disabled")

    def unique_stems(selected_files: list[Path]) -> list[str]:
        used: set[str] = set()
        result: list[str] = []
        for path in selected_files:
            stem = path.stem
            candidate = stem
            index = 2
            while candidate.casefold() in used:
                candidate = f"{stem}-{index}"
                index += 1
            used.add(candidate.casefold())
            result.append(candidate)
        return result

    def worker(
        selected_files: list[Path],
        output_dir: Path,
        preset: str | None,
        qa: bool,
        review_html: bool,
        arrows: bool,
        ai_python: str | None,
        model_root: str | None,
    ) -> None:
        stems = unique_stems(selected_files)
        for index, (input_path, stem) in enumerate(zip(selected_files, stems), start=1):
            events.put(("status", f"正在转换 {index}/{len(selected_files)}：{input_path.name}"))
            arguments = build_cli_arguments(
                input_path,
                output_dir,
                preset,
                qa=qa,
                review_html=review_html,
                arrows=arrows,
                ai_python=ai_python,
                model_root=model_root,
                output_stem=stem,
            )
            stream = io.StringIO()
            try:
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                    cli_main(arguments)
            except (
                ImportError,
                KeyError,
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                ValueError,
            ) as exc:
                events.put(("log", stream.getvalue()))
                events.put(("error", f"{input_path.name}: {exc}"))
                return
            events.put(("log", stream.getvalue()))
            events.put(("progress", str(index)))
        events.put(("done", str(output_dir)))

    def start() -> None:
        if running.get():
            return
        if not files:
            messagebox.showwarning("image2svg", "请先选择图片。")
            return
        output_dir = Path(output_var.get()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        running.set(True)
        start_button.configure(state="disabled")
        progress.configure(maximum=len(files), value=0)
        append_log(f"输出目录：{output_dir}")
        thread = threading.Thread(
            target=worker,
            args=(
                list(files),
                output_dir,
                PRESET_LABELS[preset_var.get()],
                qa_var.get(),
                review_var.get(),
                arrows_var.get(),
                ai_python_var.get().strip() or None,
                model_root_var.get().strip() or None,
            ),
            daemon=True,
        )
        thread.start()

    def poll_events() -> None:
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "status":
                    status_var.set(value)
                elif kind == "log":
                    if value.strip():
                        append_log(value)
                elif kind == "progress":
                    progress.configure(value=int(value))
                elif kind == "error":
                    running.set(False)
                    start_button.configure(state="normal")
                    status_var.set("转换失败")
                    messagebox.showerror("image2svg", value)
                elif kind == "done":
                    running.set(False)
                    start_button.configure(state="normal")
                    status_var.set("转换完成")
                    messagebox.showinfo("image2svg", f"转换完成\n{value}")
        except queue.Empty:
            pass
        root.after(150, poll_events)

    start_button.configure(command=start)
    root.after(150, poll_events)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
