from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox

import customtkinter as ctk

from cime import (
    APP_VERSION,
    CimeDownloaderError,
    DownloadCancelled,
    ProgressSnapshot,
    VideoInfo,
    build_output_path,
    download_with_ffmpeg,
    get_video_info,
    suggest_filename,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WINDOW_BG = "#121212"
SURFACE = "#1e1e1e"
SURFACE_ALT = "#252525"
SURFACE_RAISED = "#333333"
BORDER = "#3a3a3a"
TEXT_PRIMARY = "#f1f1f1"
TEXT_MUTED = "#a7a7a7"
ACCENT = "#21a366"
ACCENT_HOVER = "#1a8553"
ACCENT_STRONG = "#28c279"
DANGER = "#532121"
DANGER_BORDER = "#ae3333"
SUCCESS = "#1f4d32"
SUCCESS_BORDER = "#2f8851"
WARNING = "#5b4a20"
WARNING_BORDER = "#b38d28"
LOG_BG = "#151515"


class QueueCard(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.preview = ctk.CTkFrame(
            self,
            width=100,
            height=64,
            fg_color="#303030",
            corner_radius=8,
        )
        self.preview.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=12, pady=12)
        self.preview.grid_propagate(False)

        self.preview_label = ctk.CTkLabel(
            self.preview,
            text="VIDEO",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")

        self.title_var = tk.StringVar(value="Queue is empty")
        self.message_var = tk.StringVar(value="Waiting for a link...")
        self.meta_var = tk.StringVar(value="")
        self.badge_var = tk.StringVar(value="IDLE")

        self.title_label = ctk.CTkLabel(
            self,
            textvariable=self.title_var,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.title_label.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 0))

        self.badge = ctk.CTkLabel(
            self,
            textvariable=self.badge_var,
            fg_color=SURFACE_RAISED,
            corner_radius=6,
            padx=8,
            pady=2,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self.badge.grid(row=0, column=2, sticky="ne", padx=(0, 12), pady=(12, 0))

        self.message_label = ctk.CTkLabel(
            self,
            textvariable=self.message_var,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_MUTED,
        )
        self.message_label.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(2, 2))

        self.meta_label = ctk.CTkLabel(
            self,
            textvariable=self.meta_var,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        )
        self.meta_label.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 12))

    def apply_state(self, state: str, title: str, message: str, meta: str) -> None:
        styles = {
            "idle": (SURFACE, BORDER, SURFACE_RAISED, TEXT_MUTED, "#303030"),
            "fetching": (SURFACE, ACCENT, ACCENT, "#ffffff", "#1a4d35"),
            "ready": (SURFACE, BORDER, SURFACE_RAISED, TEXT_MUTED, "#303030"),
            "queued": (SURFACE, ACCENT, ACCENT, "#ffffff", "#1a4d35"),
            "downloading": (SURFACE, ACCENT_STRONG, ACCENT_STRONG, "#ffffff", "#1a4d35"),
            "completed": (SURFACE, SUCCESS_BORDER, SUCCESS_BORDER, "#ffffff", "#1a4d35"),
            "cancelled": (SURFACE, WARNING_BORDER, WARNING_BORDER, "#ffffff", "#4d3a1a"),
            "error": (SURFACE, DANGER_BORDER, DANGER_BORDER, "#ffffff", "#4d1a1a"),
        }
        card_bg, card_border, badge_bg, badge_text, preview_bg = styles[state]

        self.configure(fg_color=card_bg, border_color=card_border)
        self.preview.configure(fg_color=preview_bg)
        self.badge.configure(fg_color=badge_bg, text_color=badge_text)
        self.title_var.set(title)
        self.message_var.set(message)
        self.meta_var.set(meta)
        self.badge_var.set(state.upper())


class CimeDownloaderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=WINDOW_BG)

        self.title(f"cime Downloader v{APP_VERSION}")
        self.geometry("940x680")
        self.minsize(900, 640)

        self.queue: Queue[tuple[str, object]] = Queue()
        self.stop_event = Event()
        self.is_fetching = False
        self.is_downloading = False
        self.progress_indeterminate = False
        self.loaded_url = ""
        self.video_info: VideoInfo | None = None
        self.last_suggested_filename = "downloaded_cime_video.mp4"

        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(self._default_download_dir()))
        self.file_name_var = tk.StringVar(value=self.last_suggested_filename)
        self.status_var = tk.StringVar(value="Ready")
        self.detail_var = tk.StringVar(value="0 MB / estimated")
        self.speed_var = tk.StringVar(value="-")
        self.queue_count_var = tk.StringVar(value="0 / 1")
        self.folder_summary_var = tk.StringVar(value=self._compact_path(self.output_dir_var.get()))
        self.file_summary_var = tk.StringVar(value=self.file_name_var.get())

        self.smart_mode_enabled = False
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.after(150, self._poll_queue)

    def _build_ui(self) -> None:
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=20, pady=18)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)

        self._build_header(shell)
        self._build_settings(shell)
        self._build_queue_area(shell)
        self._build_footer(shell)

        self._set_task_visual(
            "idle",
            "Queue is empty",
            "Click '+ Paste Link' to start downloading.",
            "ready",
        )
        self.log("App ready. Modernized UI enabled.")
        self._sync_controls()

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(header, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        toolbar.grid_columnconfigure(1, weight=1)

        self.paste_link_button = ctk.CTkButton(
            toolbar,
            text="+ Paste Link",
            width=140,
            height=40,
            corner_radius=8,
            command=self.paste_and_download,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.paste_link_button.grid(row=0, column=0, padx=(5, 10))

        self.smart_mode_button = ctk.CTkButton(
            toolbar,
            text="💡 Smart Mode",
            width=130,
            height=40,
            corner_radius=8,
            command=self.toggle_smart_mode,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=13),
        )
        self.smart_mode_button.grid(row=0, column=1, sticky="w")

        self.mini_progress = ctk.CTkProgressBar(
            toolbar,
            width=120,
            height=8,
            corner_radius=999,
            progress_color=ACCENT,
            fg_color=SURFACE_RAISED,
        )
        self.mini_progress.grid(row=0, column=2, padx=(10, 5))
        self.mini_progress.set(0)

    def _build_settings(self, parent: ctk.CTkFrame) -> None:
        self.settings_frame = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        # self.settings_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        self.paste_button = ctk.CTkButton(
            self.settings_frame,
            text="Manual Paste",
            width=82,
            height=32,
            corner_radius=8,
            command=self.paste_and_download,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.paste_button.grid(row=0, column=0, padx=(10, 8), pady=10)

        self.folder_button = ctk.CTkButton(
            self.settings_frame,
            text="폴더",
            width=70,
            height=32,
            corner_radius=8,
            command=self.choose_folder,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.folder_button.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=10)

        self.folder_label = ctk.CTkLabel(
            self.settings_frame,
            textvariable=self.folder_summary_var,
            anchor="w",
            justify="left",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.folder_label.grid(row=0, column=2, sticky="ew", padx=(0, 16), pady=10)

        self.file_entry = ctk.CTkEntry(
            self.settings_frame,
            textvariable=self.file_name_var,
            height=32,
            corner_radius=8,
            border_color=BORDER,
            fg_color="#232323",
            text_color=TEXT_PRIMARY,
            placeholder_text="파일명",
        )
        self.file_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=10)
        self.file_name_var.trace_add("write", self._refresh_file_summary)

        self.overwrite_switch = ctk.CTkSwitch(
            self.settings_frame,
            text="덮어쓰기",
            progress_color=ACCENT,
            button_color=TEXT_PRIMARY,
            button_hover_color=TEXT_PRIMARY,
            switch_width=44,
            switch_height=22,
            text_color=TEXT_PRIMARY,
        )
        self.overwrite_switch.select()
        self.overwrite_switch.grid(row=0, column=4, padx=(0, 10), pady=10)

        self.open_folder_button = ctk.CTkButton(
            self.settings_frame,
            text="열기",
            width=70,
            height=32,
            corner_radius=8,
            command=self.open_output_folder,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.open_folder_button.grid(row=0, column=5, padx=(0, 10), pady=10)

    def _build_queue_area(self, parent: ctk.CTkFrame) -> None:
        self.queue_area = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        self.queue_area.grid(row=2, column=0, sticky="nsew")
        body = self.queue_area
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        body.grid_rowconfigure(3, weight=0)

        queue_header = ctk.CTkFrame(body, fg_color="transparent")
        queue_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        queue_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            queue_header,
            text="Queue",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            queue_header,
            textvariable=self.queue_count_var,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=1, sticky="e")

        self.queue_frame = ctk.CTkScrollableFrame(
            body,
            fg_color="#1d1d1d",
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        self.queue_frame.grid_columnconfigure(0, weight=1)

        self.task_card = QueueCard(self.queue_frame)
        self.task_card.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 8))

        info_strip = ctk.CTkFrame(
            body,
            fg_color=SURFACE_ALT,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        info_strip.grid(row=2, column=0, sticky="ew", padx=10, pady=(10, 8))
        info_strip.grid_columnconfigure(0, weight=1)
        info_strip.grid_columnconfigure(1, weight=1)
        info_strip.grid_columnconfigure(2, weight=1)

        self.progress_value_label = ctk.CTkLabel(
            info_strip,
            text="READY",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.progress_value_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))

        self.speed_value_label = ctk.CTkLabel(
            info_strip,
            textvariable=self.speed_var,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.speed_value_label.grid(row=0, column=1, sticky="w", padx=12, pady=(10, 0))

        self.detail_value_label = ctk.CTkLabel(
            info_strip,
            textvariable=self.detail_var,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.detail_value_label.grid(row=0, column=2, sticky="w", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            info_strip,
            text="state",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            info_strip,
            text="speed",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=1, sticky="w", padx=12, pady=(0, 10))

        ctk.CTkLabel(
            info_strip,
            text="transfer",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).grid(row=1, column=2, sticky="w", padx=12, pady=(0, 10))

        self.log_shell = ctk.CTkFrame(
            body,
            fg_color=LOG_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        # self.log_shell.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.log_shell.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(self.log_shell, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header,
            text="Log",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        self.clear_log_button = ctk.CTkButton(
            log_header,
            text="clear",
            width=56,
            height=24,
            corner_radius=8,
            command=self.clear_log,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
        )
        self.clear_log_button.grid(row=0, column=1, sticky="e")

        self.log_text = ctk.CTkTextbox(
            self.log_shell,
            height=78,
            fg_color="transparent",
            text_color=TEXT_PRIMARY,
            border_width=0,
            font=ctk.CTkFont(family="Cascadia Mono", size=12),
            wrap="word",
        )
        self.log_text.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        self.log_text.configure(state="disabled")

    def _build_footer(self, parent: ctk.CTkFrame) -> None:
        footer = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(0, weight=1)

        self.progressbar = ctk.CTkProgressBar(
            footer,
            height=8,
            corner_radius=999,
            progress_color=ACCENT,
            fg_color=SURFACE_RAISED,
        )
        self.progressbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        self.progressbar.set(0)

        bottom_row = ctk.CTkFrame(footer, fg_color="transparent")
        bottom_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        bottom_row.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            bottom_row,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.log_toggle_button = ctk.CTkButton(
            bottom_row,
            text="Show Log",
            width=80,
            height=28,
            corner_radius=8,
            command=self.toggle_log,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.log_toggle_button.grid(row=0, column=1, padx=(0, 10))

        self.cancel_button = ctk.CTkButton(
            bottom_row,
            text="취소",
            width=72,
            height=28,
            corner_radius=8,
            command=self.cancel_download,
            fg_color=SURFACE_RAISED,
            hover_color="#383838",
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.cancel_button.grid(row=0, column=2, padx=(0, 0))

    def paste_and_download(self) -> None:
        try:
            value = self.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("Empty Clipboard", "No URL found in clipboard.")
            return
        if not value:
            messagebox.showinfo("Empty Clipboard", "No URL found in clipboard.")
            return

        self.url_var.set(value)
        self.log(f"Pasted URL from clipboard: {value}")
        self.start_download()

    def toggle_smart_mode(self) -> None:
        self.smart_mode_enabled = not self.smart_mode_enabled
        if self.smart_mode_enabled:
            self.settings_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
            self.smart_mode_button.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER)
        else:
            self.settings_frame.grid_forget()
            self.smart_mode_button.configure(fg_color=SURFACE_RAISED, hover_color="#383838")

    def toggle_log(self) -> None:
        if self.log_shell.winfo_manager():
            self.log_shell.grid_forget()
            self.log_toggle_button.configure(text="Show Log")
        else:
            self.log_shell.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
            self.log_toggle_button.configure(text="Hide Log")

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if selected:
            self.output_dir_var.set(selected)
            self.folder_summary_var.set(self._compact_path(selected))
            self.log(f"저장 폴더를 변경했습니다: {selected}")

    def open_output_folder(self) -> None:
        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log("로그를 초기화했습니다.")

    def fetch_info(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL 필요", "ci.me VOD URL을 입력해 주세요.")
            return
        if self.is_fetching or self.is_downloading:
            return

        self.is_fetching = True
        self._sync_controls()
        self.status_var.set("페이지와 메타데이터를 확인하는 중입니다.")
        self.progress_value_label.configure(text="SCAN")
        self._set_task_visual(
            "fetching",
            self._display_title(url),
            "페이지를 확인하고 m3u8 URL을 찾는 중입니다.",
            self._build_meta_line(url, "validating source"),
        )
        self.log(f"페이지 정보 조회 시작: {url}")

        Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL 필요", "ci.me VOD URL을 입력해 주세요.")
            return
        if self.is_fetching or self.is_downloading:
            return

        raw_name = self.file_name_var.get().strip() or self.last_suggested_filename
        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        self.stop_event = Event()
        self.is_downloading = True
        self._sync_controls()
        self._set_progress_idle()
        self.status_var.set("다운로드 준비 중입니다.")
        self.progress_value_label.configure(text="QUEUE")
        self._set_task_visual(
            "queued",
            self._display_title(self.detected_title_from_state(url)),
            "출력 경로를 점검하고 다운로드를 시작할 준비를 하고 있습니다.",
            self._build_meta_line(str(folder), raw_name),
        )
        self.log(f"다운로드 요청: {url}")

        Thread(
            target=self._download_worker,
            args=(url, folder, raw_name, self.overwrite_switch.get()),
            daemon=True,
        ).start()

    def cancel_download(self) -> None:
        if not self.is_downloading:
            return
        self.stop_event.set()
        self.status_var.set("다운로드 취소 요청을 보냈습니다.")
        self.progress_value_label.configure(text="STOP")
        self.log("다운로드 취소 요청")

    def _fetch_info_worker(self, url: str) -> None:
        try:
            info = get_video_info(url)
            self.queue.put(("info_loaded", info))
        except Exception as exc:
            self.queue.put(("task_error", exc))
        finally:
            self.queue.put(("fetch_finished", None))

    def _download_worker(self, url: str, folder: Path, raw_name: str, overwrite: bool) -> None:
        try:
            info = self.video_info if self.loaded_url == url and self.video_info else get_video_info(url)
            if self.loaded_url != url:
                self.queue.put(("info_loaded", info))

            requested_name = raw_name or suggest_filename(info.title)
            output_path = build_output_path(folder, requested_name)
            final_path = download_with_ffmpeg(
                info.m3u8_url,
                output_path,
                progress_callback=lambda snapshot: self.queue.put(("progress", snapshot)),
                overwrite=overwrite,
                stop_event=self.stop_event,
            )
            self.queue.put(("download_completed", final_path))
        except Exception as exc:
            self.queue.put(("task_error", exc))
        finally:
            self.queue.put(("download_finished", None))

    def _poll_queue(self) -> None:
        try:
            while True:
                event, payload = self.queue.get_nowait()
                self._handle_event(event, payload)
        except Empty:
            pass
        finally:
            self.after(150, self._poll_queue)

    def _handle_event(self, event: str, payload: object) -> None:
        if event == "info_loaded":
            info = payload
            assert isinstance(info, VideoInfo)
            previous_suggestion = self.last_suggested_filename

            self.video_info = info
            self.loaded_url = info.page_url
            self.last_suggested_filename = suggest_filename(info.title)

            current_name = self.file_name_var.get().strip()
            if current_name in {"", previous_suggestion, "downloaded_cime_video.mp4"}:
                self.file_name_var.set(self.last_suggested_filename)
            self.file_summary_var.set(self.file_name_var.get().strip() or self.last_suggested_filename)

            if not self.is_downloading:
                self.status_var.set("페이지 정보를 불러왔습니다.")
                self.progress_value_label.configure(text="READY")

            self._set_task_visual(
                "ready",
                self._display_title(info.title or info.page_url),
                "메타데이터 확인 완료. 다운로드 준비가 되었습니다.",
                self._build_meta_line(self.output_dir_var.get(), self.file_name_var.get()),
            )
            self.log(f"제목 감지: {info.title or '없음'}")
            return

        if event == "progress":
            snapshot = payload
            assert isinstance(snapshot, ProgressSnapshot)
            self._apply_progress(snapshot)
            return

        if event == "download_completed":
            final_path = payload
            assert isinstance(final_path, Path)
            self._stop_indeterminate()
            self.progressbar.set(1)
            self.mini_progress.set(1)
            self.status_var.set(f"완료: {final_path.name}")
            self.progress_value_label.configure(text="DONE")
            self._set_task_visual(
                "completed",
                final_path.name,
                "다운로드가 완료되었습니다.",
                self._build_meta_line(str(final_path.parent), final_path.name),
            )
            self.log(f"다운로드 완료: {final_path}")
            messagebox.showinfo("다운로드 완료", f"파일이 저장되었습니다.\n{final_path}")
            return

        if event == "task_error":
            error = payload
            assert isinstance(error, Exception)
            self._stop_indeterminate()
            self.progress_value_label.configure(text="ERROR")

            if isinstance(error, DownloadCancelled):
                self.status_var.set(str(error))
                self._set_task_visual(
                    "cancelled",
                    self._display_title(self.detected_title_from_state(self.url_var.get().strip())),
                    str(error),
                    self._build_meta_line(self.output_dir_var.get(), self.file_name_var.get()),
                )
                self.log(str(error))
                return

            if isinstance(error, FileExistsError):
                message = str(error)
            elif isinstance(error, CimeDownloaderError):
                message = str(error)
            else:
                message = f"예상치 못한 오류: {error}"

            self.status_var.set(message)
            self._set_task_visual(
                "error",
                self._display_title(self.detected_title_from_state(self.url_var.get().strip())),
                message,
                self._build_meta_line(self.output_dir_var.get(), self.file_name_var.get()),
            )
            self.log(message)
            messagebox.showerror("오류", message)
            return

        if event == "fetch_finished":
            self.is_fetching = False
            self._sync_controls()
            return

        if event == "download_finished":
            self.is_downloading = False
            self._sync_controls()
            return

    def _apply_progress(self, snapshot: ProgressSnapshot) -> None:
        if snapshot.state == "starting":
            self.status_var.set(snapshot.message)
            self.progress_value_label.configure(text="START")
            self.detail_var.set("0 MB / estimated")
            self._start_indeterminate()
            self._set_task_visual(
                "downloading",
                self._display_title(self.detected_title_from_state(snapshot.output_path.name)),
                snapshot.message,
                self._build_meta_line(str(snapshot.output_path.parent), snapshot.output_path.name),
            )
            self.log(snapshot.message)
            return

        if snapshot.state == "running":
            if snapshot.percent is None:
                self._start_indeterminate()
                self.progress_value_label.configure(text="SCAN")
            else:
                self._stop_indeterminate()
                fraction = snapshot.percent / 100
                self.progressbar.set(fraction)
                self.mini_progress.set(fraction)
                self.progress_value_label.configure(text=f"{snapshot.percent:.1f}%")

            downloaded = self._format_size(snapshot.downloaded_bytes)
            estimated = self._format_size(snapshot.estimated_total_bytes)
            speed = self._format_speed(snapshot.speed_bytes_per_second)
            self.status_var.set(snapshot.message)
            self.detail_var.set(f"{downloaded} / {estimated}")
            self.speed_var.set(speed)
            self._set_task_visual(
                "downloading",
                self._display_title(self.detected_title_from_state(snapshot.output_path.name)),
                snapshot.message,
                f"{downloaded} / {estimated}   {speed}",
            )
            return

        if snapshot.state == "completed":
            self._stop_indeterminate()
            self.progressbar.set(1)
            self.mini_progress.set(1)
            self.detail_var.set(
                f"{self._format_size(snapshot.downloaded_bytes)} / {self._format_size(snapshot.estimated_total_bytes)}"
            )
            self.speed_var.set("-")
            return

        if snapshot.state in {"cancelled", "error"}:
            self._stop_indeterminate()
            self.speed_var.set("-")

    def _sync_controls(self) -> None:
        busy = self.is_fetching or self.is_downloading
        action_state = "disabled" if busy else "normal"
        cancel_state = "normal" if self.is_downloading else "disabled"

        self.paste_link_button.configure(state=action_state)
        self.paste_button.configure(state=action_state)
        self.folder_button.configure(state=action_state)
        self.open_folder_button.configure(state="normal")
        self.cancel_button.configure(state=cancel_state)

        if self.is_downloading or self.is_fetching or self.video_info:
            self.queue_count_var.set("1 / 1")
        else:
            self.queue_count_var.set("0 / 1")

    def _start_indeterminate(self) -> None:
        if self.progress_indeterminate:
            return
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start()
        self.progress_indeterminate = True

    def _stop_indeterminate(self) -> None:
        if self.progress_indeterminate:
            self.progressbar.stop()
        self.progressbar.configure(mode="determinate")
        self.progress_indeterminate = False

    def _set_progress_idle(self) -> None:
        self._stop_indeterminate()
        self.progressbar.set(0)
        self.mini_progress.set(0)
        self.detail_var.set("0 MB / estimated")
        self.speed_var.set("-")

    def _set_task_visual(self, state: str, title: str, message: str, meta: str) -> None:
        self.task_card.apply_state(state, title, message, meta)

    def _handle_close(self) -> None:
        if self.is_downloading:
            should_close = messagebox.askyesno(
                "다운로드 중",
                "다운로드가 진행 중입니다. 취소하고 창을 닫을까요?",
            )
            if not should_close:
                return
            self.stop_event.set()
        self.destroy()

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def detected_title_from_state(self, fallback: str) -> str:
        if self.video_info and self.video_info.title:
            return self.video_info.title
        return fallback or "Untitled item"

    def _display_title(self, text: str) -> str:
        if not text:
            return "Untitled item"
        return text if len(text) <= 70 else text[:67] + "..."

    def _build_meta_line(self, left: str, right: str) -> str:
        return f"{self._compact_path(left)}   {right}"

    def _refresh_file_summary(self, *_args: object) -> None:
        value = self.file_name_var.get().strip() or self.last_suggested_filename
        self.file_summary_var.set(value)

    @staticmethod
    def _default_download_dir() -> Path:
        downloads = Path.home() / "Downloads"
        return downloads if downloads.exists() else Path.cwd()

    @staticmethod
    def _format_size(value: int | None) -> str:
        if value is None:
            return "estimated"
        return f"{value / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_speed(value: int | None) -> str:
        if not value:
            return "-"
        return f"{value / (1024 * 1024):.1f} MB/s"

    @staticmethod
    def _compact_path(value: str) -> str:
        if not value:
            return "-"
        compact = str(Path(value).expanduser())
        return compact if len(compact) <= 38 else "..." + compact[-35:]


def main() -> None:
    app = CimeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
