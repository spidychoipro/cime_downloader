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

BACKGROUND = "#0b1017"
SURFACE = "#111826"
PANEL = "#171f2f"
PANEL_ALT = "#1b2638"
LOG_BG = "#090d14"
BORDER = "#273449"
ACCENT = "#46c5ff"
ACCENT_HOVER = "#2ba8df"
ACCENT_WARM = "#ff7a45"
ACCENT_WARM_HOVER = "#ff6232"
TEXT_PRIMARY = "#f5f7fb"
TEXT_MUTED = "#93a2b8"
SUCCESS = "#38d39f"
WARNING = "#f6c85f"


class InfoCard(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, title: str, variable: tk.StringVar) -> None:
        super().__init__(
            parent,
            fg_color=PANEL_ALT,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=title,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            self,
            textvariable=variable,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=240,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))


class CimeDownloaderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BACKGROUND)

        self.title(f"cime Downloader v{APP_VERSION}")
        self.geometry("1240x820")
        self.minsize(1120, 760)

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
        self.detected_title_var = tk.StringVar(value="아직 불러오지 않음")
        self.status_var = tk.StringVar(value="ci.me 링크를 붙여넣고 메타데이터를 먼저 확인해 주세요.")
        self.detail_var = tk.StringVar(value="0 MB / 추정 중")
        self.speed_var = tk.StringVar(value="-")
        self.progress_text_var = tk.StringVar(value="READY")
        self.security_var = tk.StringVar(value="ci.me 전용 URL 검증, mp4 고정, 폴더 탈출 차단이 기본 활성화됩니다.")
        self.queue_state_var = tk.StringVar(value="1 task panel")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.after(150, self._poll_queue)

    def _build_ui(self) -> None:
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=20, pady=20)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        self.sidebar = self._build_sidebar(shell)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 18))

        content = ctk.CTkFrame(shell, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(3, weight=1)

        self._build_header(content)
        self._build_source_card(content)
        self._build_insight_card(content)
        self._build_output_card(content)
        self._build_progress_card(content)
        self._build_log_card(content)

        self.url_entry.focus_set()
        self.log("앱이 준비되었습니다. v0.2 레이아웃과 보안 가드가 활성화되었습니다.")
        self._sync_controls()

    def _build_sidebar(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        sidebar = ctk.CTkFrame(
            parent,
            width=292,
            fg_color=SURFACE,
            corner_radius=28,
            border_width=1,
            border_color=BORDER,
        )
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="cime\nDownloader",
            font=ctk.CTkFont(size=33, weight="bold"),
            text_color=TEXT_PRIMARY,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(26, 8))

        ctk.CTkLabel(
            sidebar,
            text="Hitomi Downloader의 어두운 작업실 감성을 참고해 재정비한 ci.me 전용 데스크톱 UI입니다.",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=240,
        ).grid(row=1, column=0, sticky="ew", padx=24)

        self.mode_badge = ctk.CTkLabel(
            sidebar,
            text="READY",
            fg_color=SUCCESS,
            text_color=BACKGROUND,
            corner_radius=999,
            font=ctk.CTkFont(size=12, weight="bold"),
            padx=14,
            pady=7,
        )
        self.mode_badge.grid(row=2, column=0, sticky="w", padx=24, pady=(18, 18))

        ctk.CTkLabel(
            sidebar,
            text="Workspace",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=3, column=0, sticky="w", padx=24)

        ctk.CTkLabel(
            sidebar,
            textvariable=self.queue_state_var,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=4, column=0, sticky="w", padx=24, pady=(4, 18))

        ctk.CTkLabel(
            sidebar,
            text="Security guardrails",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=5, column=0, sticky="w", padx=24)

        guardrail_texts = [
            "ci.me VOD URL만 허용",
            "리디렉션 뒤 호스트 재검증",
            "파일명에 경로 입력 차단",
            "ffmpeg를 -nostdin 으로 실행",
        ]
        for index, line in enumerate(guardrail_texts, start=6):
            item = ctk.CTkFrame(sidebar, fg_color="transparent")
            item.grid(row=index, column=0, sticky="ew", padx=24, pady=(10 if index == 6 else 6, 0))
            ctk.CTkLabel(
                item,
                text="●",
                text_color=ACCENT,
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                item,
                text=line,
                text_color=TEXT_PRIMARY,
                font=ctk.CTkFont(size=13),
                justify="left",
            ).pack(side="left")

        footer = ctk.CTkFrame(sidebar, fg_color=PANEL_ALT, corner_radius=20, border_width=1, border_color=BORDER)
        footer.grid(row=10, column=0, sticky="ew", padx=20, pady=(18, 22))
        ctk.CTkLabel(
            footer,
            text="v0.2",
            text_color=ACCENT_WARM,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            footer,
            text="queue형 로그 레이아웃, 더 큰 상태 카드, 안전한 출력 경로 생성으로 전반을 손봤습니다.",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=232,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        return sidebar

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Modernized ci.me download desk",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="분석, 저장 설정, 진행 상태, 로그를 한 화면에서 다루되 히토미 다운로더처럼 작업 흐름이 바로 보이도록 정리했습니다.",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_MUTED,
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        ctk.CTkLabel(
            header,
            text="Hitomi-inspired UI reference",
            fg_color=PANEL,
            corner_radius=999,
            text_color=ACCENT,
            font=ctk.CTkFont(size=12, weight="bold"),
            padx=14,
            pady=8,
        ).grid(row=0, column=1, sticky="e", rowspan=2)

    def _build_source_card(self, parent: ctk.CTkFrame) -> None:
        card, body = self._create_card(
            parent,
            row=1,
            column=0,
            title="Source",
            subtitle="ci.me VOD 링크를 붙여넣고 분석한 다음 안전하게 다운로드하세요.",
        )
        card.grid_rowconfigure(2, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=1)

        self.url_entry = ctk.CTkEntry(
            body,
            textvariable=self.url_var,
            height=50,
            corner_radius=16,
            border_color=BORDER,
            fg_color=PANEL_ALT,
            text_color=TEXT_PRIMARY,
            placeholder_text="https://ci.me/@username/vods/123456",
        )
        self.url_entry.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.url_entry.bind("<Return>", lambda _event: self.fetch_info())

        self.paste_button = ctk.CTkButton(
            body,
            text="붙여넣기",
            command=self.paste_url,
            height=42,
            corner_radius=14,
            fg_color=PANEL_ALT,
            hover_color=PANEL,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.paste_button.grid(row=1, column=0, sticky="ew", pady=(14, 0), padx=(0, 8))

        self.fetch_button = ctk.CTkButton(
            body,
            text="정보 불러오기",
            command=self.fetch_info,
            height=42,
            corner_radius=14,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=BACKGROUND,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.fetch_button.grid(row=1, column=1, sticky="ew", pady=(14, 0), padx=8)

        self.quick_button = ctk.CTkButton(
            body,
            text="바로 다운로드",
            command=self.start_download,
            height=42,
            corner_radius=14,
            fg_color=ACCENT_WARM,
            hover_color=ACCENT_WARM_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.quick_button.grid(row=1, column=2, sticky="ew", pady=(14, 0), padx=(8, 0))

        preview = ctk.CTkFrame(body, fg_color=PANEL_ALT, corner_radius=18, border_width=1, border_color=BORDER)
        preview.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        preview.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            preview,
            text="Detected title",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            preview,
            textvariable=self.detected_title_var,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
            justify="left",
            anchor="w",
            wraplength=640,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            preview,
            text="분석된 제목은 기본 파일명 제안으로 연결되며, 사용자가 직접 수정하면 이후에는 덮어쓰지 않습니다.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=640,
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _build_insight_card(self, parent: ctk.CTkFrame) -> None:
        _, body = self._create_card(
            parent,
            row=1,
            column=1,
            title="Insight",
            subtitle="다운로드 상태를 카드형으로 바로 읽을 수 있게 배치했습니다.",
        )
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self.progress_card = InfoCard(body, "진행 상태", self.progress_text_var)
        self.progress_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))

        self.speed_card = InfoCard(body, "속도", self.speed_var)
        self.speed_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        self.detail_card = InfoCard(body, "전송량", self.detail_var)
        self.detail_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 12))

        security_panel = ctk.CTkFrame(
            body,
            fg_color=PANEL_ALT,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        security_panel.grid(row=2, column=0, columnspan=2, sticky="nsew")
        security_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            security_panel,
            text="Security note",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            security_panel,
            textvariable=self.security_var,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=330,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _build_output_card(self, parent: ctk.CTkFrame) -> None:
        _, body = self._create_card(
            parent,
            row=2,
            column=0,
            title="Destination",
            subtitle="저장 폴더와 파일명을 확인하고, 같은 이름 충돌 처리까지 선택하세요.",
        )
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            body,
            text="저장 폴더",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkEntry(
            body,
            textvariable=self.output_dir_var,
            height=44,
            corner_radius=14,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 10))

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.grid(row=1, column=1, sticky="e", pady=(8, 0))

        self.browse_button = ctk.CTkButton(
            controls,
            text="폴더 선택",
            command=self.choose_folder,
            height=44,
            corner_radius=14,
            fg_color=PANEL_ALT,
            hover_color=PANEL,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.browse_button.pack(side="left", padx=(0, 8))

        self.open_folder_button = ctk.CTkButton(
            controls,
            text="열기",
            command=self.open_output_folder,
            height=44,
            width=82,
            corner_radius=14,
            fg_color=PANEL_ALT,
            hover_color=PANEL,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.open_folder_button.pack(side="left")

        ctk.CTkLabel(
            body,
            text="파일명",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", pady=(18, 0))

        ctk.CTkEntry(
            body,
            textvariable=self.file_name_var,
            height=44,
            corner_radius=14,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.overwrite_switch = ctk.CTkSwitch(
            body,
            text="같은 이름이 있으면 자동으로 덮어쓰기",
            progress_color=ACCENT,
            button_color=TEXT_PRIMARY,
            button_hover_color=TEXT_PRIMARY,
            switch_width=48,
            switch_height=24,
            text_color=TEXT_PRIMARY,
        )
        self.overwrite_switch.select()
        self.overwrite_switch.grid(row=4, column=0, columnspan=2, sticky="w", pady=(18, 0))

        ctk.CTkLabel(
            body,
            text="확장자는 항상 mp4로 고정되며, 폴더 경로를 파일명에 섞어 넣을 수 없도록 막아 두었습니다.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            wraplength=680,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_progress_card(self, parent: ctk.CTkFrame) -> None:
        _, body = self._create_card(
            parent,
            row=2,
            column=1,
            title="Transfer",
            subtitle="다운로드 진행률과 작업 액션을 오른쪽 패널에 모았습니다.",
        )
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            textvariable=self.progress_text_var,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=38, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            body,
            textvariable=self.status_var,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=360,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.progressbar = ctk.CTkProgressBar(
            body,
            height=18,
            corner_radius=999,
            progress_color=ACCENT,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            border_width=1,
        )
        self.progressbar.grid(row=2, column=0, sticky="ew", pady=(18, 8))
        self.progressbar.set(0)

        ctk.CTkLabel(
            body,
            textvariable=self.detail_var,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=13),
        ).grid(row=3, column=0, sticky="w")

        action_row = ctk.CTkFrame(body, fg_color="transparent")
        action_row.grid(row=4, column=0, sticky="ew", pady=(22, 0))
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            action_row,
            text="다운로드 시작",
            command=self.start_download,
            height=48,
            corner_radius=15,
            fg_color=ACCENT_WARM,
            hover_color=ACCENT_WARM_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            action_row,
            text="취소",
            command=self.cancel_download,
            height=48,
            corner_radius=15,
            fg_color=PANEL_ALT,
            hover_color=PANEL,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.clear_log_button = ctk.CTkButton(
            body,
            text="로그 지우기",
            command=self.clear_log,
            height=42,
            corner_radius=14,
            fg_color=PANEL_ALT,
            hover_color=PANEL,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.clear_log_button.grid(row=5, column=0, sticky="ew", pady=(12, 0))

    def _build_log_card(self, parent: ctk.CTkFrame) -> None:
        _, body = self._create_card(
            parent,
            row=3,
            column=0,
            columnspan=2,
            title="Activity log",
            subtitle="다운로드 큐를 다루는 것처럼 로그를 아래에서 계속 추적할 수 있게 했습니다.",
        )
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(
            body,
            fg_color=LOG_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=18,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Cascadia Mono", size=13),
            wrap="word",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    def _create_card(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        title: str,
        subtitle: str,
        columnspan: int = 1,
    ) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        right_padding = 18 if column == 0 and columnspan == 1 else 0

        card = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            corner_radius=24,
            border_width=1,
            border_color=BORDER,
        )
        card.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="nsew",
            pady=(0, 18),
            padx=(0, right_padding),
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 2))

        ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=740 if columnspan == 2 else 420,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 12))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 22))

        return card, body

    def paste_url(self) -> None:
        try:
            value = self.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("클립보드 비어 있음", "붙여넣을 URL이 없습니다.")
            return
        if not value:
            messagebox.showinfo("클립보드 비어 있음", "붙여넣을 URL이 없습니다.")
            return

        self.url_var.set(value)
        self.log("클립보드에서 URL을 붙여넣었습니다.")

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if selected:
            self.output_dir_var.set(selected)
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
        self.status_var.set("메타데이터와 보안 검증을 진행하고 있습니다.")
        self.progress_text_var.set("SCAN")
        self.security_var.set("URL 호스트와 리디렉션 경로를 확인하는 중입니다.")
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
        self.progress_text_var.set("QUEUE")
        self.security_var.set("출력 경로를 검증하고 ffmpeg를 -nostdin으로 실행할 준비를 하고 있습니다.")
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
        self.progress_text_var.set("STOP")
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
            self.detected_title_var.set(info.title or "제목을 찾지 못함")
            self.last_suggested_filename = suggest_filename(info.title)

            current_name = self.file_name_var.get().strip()
            if current_name in {"", previous_suggestion, "downloaded_cime_video.mp4"}:
                self.file_name_var.set(self.last_suggested_filename)

            if not self.is_downloading:
                self.status_var.set("페이지 정보를 불러왔습니다.")
                self.progress_text_var.set("READY")
            self.security_var.set("ci.me 호스트 검증 완료, m3u8 URL 확인 완료, 파일명은 mp4로 잠금됩니다.")
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
            self.status_var.set(f"완료: {final_path.name}")
            self.progress_text_var.set("100%")
            self.security_var.set("검증된 경로에 저장을 마쳤습니다.")
            self.log(f"다운로드 완료: {final_path}")
            messagebox.showinfo("다운로드 완료", f"파일이 저장되었습니다.\n{final_path}")
            return

        if event == "task_error":
            error = payload
            assert isinstance(error, Exception)
            self._stop_indeterminate()
            self.progress_text_var.set("ERROR")
            self.security_var.set("작업이 중단되었습니다. URL, 파일명, ffmpeg 상태를 다시 확인해 주세요.")

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
            self._sync_controls()
            return

        if event == "download_finished":
            self.is_downloading = False
            self._sync_controls()
            return

    def _apply_progress(self, snapshot: ProgressSnapshot) -> None:
        if snapshot.state == "starting":
            self.status_var.set(snapshot.message)
            self.progress_text_var.set("START")
            self.detail_var.set("0 MB / 추정 중")
            self.security_var.set("ffmpeg를 콘솔 없이 실행했고 표준 입력은 차단했습니다.")
            self._start_indeterminate()
            self.log(snapshot.message)
            return

        if snapshot.state == "running":
            if snapshot.percent is None:
                self._start_indeterminate()
                self.progress_text_var.set("SCAN")
            else:
                self._stop_indeterminate()
                self.progressbar.set(snapshot.percent / 100)
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
            self.progressbar.set(1)
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
        fetch_state = "disabled" if busy else "normal"
        download_state = "disabled" if busy else "normal"
        cancel_state = "normal" if self.is_downloading else "disabled"

        self.fetch_button.configure(state=fetch_state)
        self.quick_button.configure(state=fetch_state)
        self.download_button.configure(state=download_state)
        self.cancel_button.configure(state=cancel_state)

        if self.is_downloading:
            self.queue_state_var.set("1 active transfer")
            self.mode_badge.configure(text="DOWNLOADING", fg_color=ACCENT_WARM, text_color=TEXT_PRIMARY)
        elif self.is_fetching:
            self.queue_state_var.set("metadata scan")
            self.mode_badge.configure(text="ANALYZING", fg_color=WARNING, text_color=BACKGROUND)
        else:
            self.queue_state_var.set("1 task panel")
            self.mode_badge.configure(text="READY", fg_color=SUCCESS, text_color=BACKGROUND)

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
