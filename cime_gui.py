from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, ttk

from cime import (
    CimeDownloaderError,
    DownloadCancelled,
    ProgressSnapshot,
    VideoInfo,
    download_with_ffmpeg,
    ensure_mp4_filename,
    get_video_info,
    suggest_filename,
)

WINDOW_BG = "#f5f1ea"
CARD_BG = "#fffaf3"
ACCENT = "#d95d39"
ACCENT_DARK = "#a63f22"
TEXT = "#2f2a24"
MUTED = "#7a6f63"
FIELD_BG = "#fffdf9"


class CimeDownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("cime Downloader UI")
        self.geometry("900x700")
        self.minsize(820, 640)
        self.configure(bg=WINDOW_BG)

        self.queue: Queue[tuple[str, object]] = Queue()
        self.stop_event = Event()
        self.is_fetching = False
        self.is_downloading = False
        self.progress_indeterminate = False
        self.loaded_url = ""
        self.video_info: VideoInfo | None = None

        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(self._default_download_dir()))
        self.file_name_var = tk.StringVar(value="downloaded_cime_video.mp4")
        self.detected_title_var = tk.StringVar(value="아직 불러오지 않음")
        self.status_var = tk.StringVar(value="URL을 입력한 뒤 정보를 불러오거나 바로 다운로드하세요.")
        self.detail_var = tk.StringVar(value="0 MB / 추정 중")
        self.speed_var = tk.StringVar(value="-")
        self.progress_text_var = tk.StringVar(value="대기 중")
        self.overwrite_var = tk.BooleanVar(value=True)

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.after(150, self._poll_queue)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Malgun Gothic", 10), foreground=TEXT)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Shell.TFrame", background=WINDOW_BG)
        style.configure("Header.TLabel", background=WINDOW_BG, font=("Malgun Gothic", 22, "bold"))
        style.configure("HeroSubheader.TLabel", background=WINDOW_BG, foreground=MUTED, font=("Malgun Gothic", 10))
        style.configure("CardSubheader.TLabel", background=CARD_BG, foreground=MUTED, font=("Malgun Gothic", 10))
        style.configure("Section.TLabel", background=CARD_BG, font=("Malgun Gothic", 11, "bold"))
        style.configure("InfoTitle.TLabel", background=CARD_BG, foreground=MUTED, font=("Malgun Gothic", 9))
        style.configure("InfoValue.TLabel", background=CARD_BG, font=("Malgun Gothic", 13, "bold"))
        style.configure("TLabel", background=CARD_BG)
        style.configure("TEntry", fieldbackground=FIELD_BG, padding=7)
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            padding=(14, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_DARK), ("disabled", "#d3c9bf")],
            foreground=[("disabled", "#f8f5f1")],
        )
        style.configure(
            "Secondary.TButton",
            background="#efe4d7",
            foreground=TEXT,
            borderwidth=0,
            padding=(14, 10),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#e4d4c2"), ("disabled", "#eee7df")],
            foreground=[("disabled", "#9d9389")],
        )
        style.configure(
            "Flat.Horizontal.TProgressbar",
            troughcolor="#ebdfd1",
            bordercolor="#ebdfd1",
            background=ACCENT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self, style="Shell.TFrame", padding=24)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        header = ttk.Frame(container, style="Shell.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="cime Downloader UI", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="CLI 스크립트를 데스크톱 다운로더처럼 사용할 수 있게 만든 UI 버전입니다.",
            style="HeroSubheader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        card = ttk.Frame(container, style="Card.TFrame", padding=22)
        card.grid(row=1, column=0, sticky="nsew")
        container.rowconfigure(1, weight=1)

        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="VOD URL", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        url_entry = ttk.Entry(card, textvariable=self.url_var)
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        self.fetch_button = ttk.Button(card, text="정보 불러오기", style="Secondary.TButton", command=self.fetch_info)
        self.fetch_button.grid(row=1, column=2, sticky="ew")

        ttk.Label(card, text="저장 폴더", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(20, 8))
        ttk.Entry(card, textvariable=self.output_dir_var).grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(card, text="폴더 선택", style="Secondary.TButton", command=self.choose_folder).grid(
            row=3, column=2, sticky="ew"
        )

        ttk.Label(card, text="파일명", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(20, 8))
        ttk.Entry(card, textvariable=self.file_name_var).grid(row=5, column=0, columnspan=3, sticky="ew")

        ttk.Checkbutton(
            card,
            text="같은 이름의 파일이 있으면 자동으로 덮어쓰기",
            variable=self.overwrite_var,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

        info_frame = ttk.Frame(card, style="Card.TFrame")
        info_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(24, 0))
        info_frame.columnconfigure((0, 1, 2), weight=1)

        self._build_info_block(info_frame, 0, "감지된 제목", self.detected_title_var)
        self._build_info_block(info_frame, 1, "진행 상태", self.progress_text_var)
        self._build_info_block(info_frame, 2, "속도", self.speed_var)

        ttk.Separator(card).grid(row=8, column=0, columnspan=3, sticky="ew", pady=20)

        ttk.Label(card, text="다운로드 진행", style="Section.TLabel").grid(row=9, column=0, sticky="w")
        self.progressbar = ttk.Progressbar(card, mode="determinate", style="Flat.Horizontal.TProgressbar")
        self.progressbar.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        ttk.Label(card, textvariable=self.status_var, style="CardSubheader.TLabel").grid(
            row=11, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(card, textvariable=self.detail_var, style="CardSubheader.TLabel").grid(
            row=12, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(22, 0))
        button_row.columnconfigure((0, 1, 2), weight=1)

        self.download_button = ttk.Button(
            button_row,
            text="다운로드 시작",
            style="Accent.TButton",
            command=self.start_download,
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ttk.Button(
            button_row,
            text="취소",
            style="Secondary.TButton",
            command=self.cancel_download,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=8)

        ttk.Button(
            button_row,
            text="폴더 열기",
            style="Secondary.TButton",
            command=self.open_output_folder,
        ).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        ttk.Label(card, text="작업 로그", style="Section.TLabel").grid(row=14, column=0, sticky="w", pady=(24, 10))
        log_shell = tk.Frame(card, bg="#eadccc", bd=0, highlightthickness=0)
        log_shell.grid(row=15, column=0, columnspan=3, sticky="nsew")
        card.rowconfigure(15, weight=1)

        self.log_text = tk.Text(
            log_shell,
            height=10,
            wrap="word",
            bg="#fffdf8",
            fg=TEXT,
            relief="flat",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

        url_entry.focus_set()
        self.log("앱이 준비되었습니다.")

    def _build_info_block(self, parent: ttk.Frame, column: int, title: str, variable: tk.StringVar) -> None:
        block = ttk.Frame(parent, style="Card.TFrame", padding=(0, 0, 12, 0))
        block.grid(row=0, column=column, sticky="ew")
        ttk.Label(block, text=title, style="InfoTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(block, textvariable=variable, style="InfoValue.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if selected:
            self.output_dir_var.set(selected)
            self.log(f"저장 폴더를 변경했습니다: {selected}")

    def fetch_info(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL 필요", "ci.me VOD URL을 입력해 주세요.")
            return
        if self.is_fetching or self.is_downloading:
            return

        self.is_fetching = True
        self._sync_buttons()
        self.status_var.set("페이지 정보를 불러오는 중입니다.")
        self.progress_text_var.set("정보 확인 중")
        self.log(f"페이지 정보 조회 시작: {url}")

        Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL 필요", "ci.me VOD URL을 입력해 주세요.")
            return
        if self.is_fetching or self.is_downloading:
            return

        raw_name = self.file_name_var.get().strip()
        if not raw_name:
            messagebox.showwarning("파일명 필요", "저장할 파일명을 입력해 주세요.")
            return

        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        self.stop_event = Event()
        self.is_downloading = True
        self._sync_buttons()
        self._set_progress_idle()
        self.status_var.set("다운로드 준비 중입니다.")
        self.progress_text_var.set("준비 중")
        self.log(f"다운로드 요청: {url}")

        Thread(
            target=self._download_worker,
            args=(url, folder, raw_name, self.overwrite_var.get()),
            daemon=True,
        ).start()

    def cancel_download(self) -> None:
        if not self.is_downloading:
            return
        self.stop_event.set()
        self.status_var.set("다운로드 취소 요청을 보냈습니다.")
        self.progress_text_var.set("취소 중")
        self.log("다운로드 취소 요청")

    def open_output_folder(self) -> None:
        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

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

            output_name = ensure_mp4_filename(raw_name) if raw_name else suggest_filename(info.title)
            output_path = folder / output_name
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
            self.video_info = info
            self.loaded_url = info.page_url
            self.detected_title_var.set(info.title or "제목을 찾지 못함")
            if (
                not self.is_downloading
                and (
                    not self.file_name_var.get().strip()
                    or self.file_name_var.get().strip() == "downloaded_cime_video.mp4"
                )
            ):
                self.file_name_var.set(suggest_filename(info.title))
            if not self.is_downloading:
                self.status_var.set("페이지 정보를 불러왔습니다.")
                self.progress_text_var.set("준비 완료")
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
            self.progressbar["value"] = 100
            self.status_var.set(f"완료: {final_path.name}")
            self.progress_text_var.set("100%")
            self.log(f"다운로드 완료: {final_path}")
            messagebox.showinfo("다운로드 완료", f"파일이 저장되었습니다.\n{final_path}")
            return

        if event == "task_error":
            error = payload
            assert isinstance(error, Exception)
            self._stop_indeterminate()
            self.progress_text_var.set("오류")
            if isinstance(error, DownloadCancelled):
                self.status_var.set(str(error))
                self.log(str(error))
                return
            if isinstance(error, FileExistsError):
                message = str(error)
            elif isinstance(error, CimeDownloaderError):
                message = str(error)
            else:
                message = f"예상치 못한 오류: {error}"
            self.status_var.set(message)
            self.log(message)
            messagebox.showerror("오류", message)
            return

        if event == "fetch_finished":
            self.is_fetching = False
            self._sync_buttons()
            return

        if event == "download_finished":
            self.is_downloading = False
            self._sync_buttons()
            return

    def _apply_progress(self, snapshot: ProgressSnapshot) -> None:
        if snapshot.state == "starting":
            self.status_var.set(snapshot.message)
            self.progress_text_var.set("시작 중")
            self.detail_var.set("0 MB / 추정 중")
            self._start_indeterminate()
            self.log(snapshot.message)
            return

        if snapshot.state == "running":
            if snapshot.percent is None:
                self._start_indeterminate()
                self.progress_text_var.set("추정 중")
            else:
                self._stop_indeterminate()
                self.progressbar["value"] = snapshot.percent
                self.progress_text_var.set(f"{snapshot.percent:.1f}%")

            downloaded = self._format_size(snapshot.downloaded_bytes)
            estimated = self._format_size(snapshot.estimated_total_bytes)
            speed = self._format_speed(snapshot.speed_bytes_per_second)
            self.status_var.set(snapshot.message)
            self.detail_var.set(f"{downloaded} / {estimated}")
            self.speed_var.set(speed)
            return

        if snapshot.state == "completed":
            self._stop_indeterminate()
            self.progressbar["value"] = 100
            self.detail_var.set(
                f"{self._format_size(snapshot.downloaded_bytes)} / {self._format_size(snapshot.estimated_total_bytes)}"
            )
            self.speed_var.set("-")
            return

        if snapshot.state in {"cancelled", "error"}:
            self._stop_indeterminate()
            self.speed_var.set("-")

    def _sync_buttons(self) -> None:
        fetch_state = "disabled" if self.is_fetching or self.is_downloading else "normal"
        download_state = "disabled" if self.is_fetching or self.is_downloading else "normal"
        cancel_state = "normal" if self.is_downloading else "disabled"
        self.fetch_button.configure(state=fetch_state)
        self.download_button.configure(state=download_state)
        self.cancel_button.configure(state=cancel_state)

    def _start_indeterminate(self) -> None:
        if self.progress_indeterminate:
            return
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(12)
        self.progress_indeterminate = True

    def _stop_indeterminate(self) -> None:
        if self.progress_indeterminate:
            self.progressbar.stop()
        self.progressbar.configure(mode="determinate")
        self.progress_indeterminate = False

    def _set_progress_idle(self) -> None:
        self._stop_indeterminate()
        self.progressbar["value"] = 0
        self.detail_var.set("0 MB / 추정 중")
        self.speed_var.set("-")

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

    @staticmethod
    def _default_download_dir() -> Path:
        downloads = Path.home() / "Downloads"
        return downloads if downloads.exists() else Path.cwd()

    @staticmethod
    def _format_size(value: int | None) -> str:
        if value is None:
            return "추정 중"
        return f"{value / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_speed(value: int | None) -> str:
        if not value:
            return "-"
        return f"{value / (1024 * 1024):.1f} MB/s"


def main() -> None:
    app = CimeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
