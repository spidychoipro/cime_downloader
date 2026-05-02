from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox

import customtkinter as ctk
# from PIL import Image (removed for portability)

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

# ====================== 시스템 설정 ======================
ctk.set_appearance_mode("dark")

# ====================== 테마 컬러 (Nebula Modern) ======================
class Theme:
    BG_MAIN = "#0B0F17"        # 심해의 어둠
    BG_SIDEBAR = "#080B11"     # 사이드바 (더 어두움)
    BG_CARD = "#151B26"        # 카드 배경
    BG_CARD_HOVER = "#1C2433"  # 카드 호버
    ACCENT = "#3B82F6"         # 프라이머리 블루
    ACCENT_LIGHT = "#60A5FA"   # 라이트 블루
    ACCENT_GRADIENT = ("#3B82F6", "#06B6D4") # 블루-시안 그라데이션 느낌
    SUCCESS = "#10B981"        # 성공/완료
    DANGER = "#EF4444"         # 오류/경고
    TEXT_PRIMARY = "#F9FAFB"   # 주 텍스트
    TEXT_SECONDARY = "#9CA3AF" # 부 텍스트
    TEXT_MUTED = "#6B7280"     # 비활성 텍스트
    BORDER = "#2D333F"         # 경계선
    TRANSPARENT = "transparent"

# ====================== 커스텀 위젯 ======================

class SidebarButton(ctk.CTkButton):
    def __init__(self, master, text, icon_text, **kwargs):
        super().__init__(
            master,
            text=f"  {icon_text}   {text}",
            anchor="w",
            height=45,
            fg_color=Theme.TRANSPARENT,
            text_color=Theme.TEXT_SECONDARY,
            hover_color=Theme.BG_CARD,
            font=ctk.CTkFont(size=14, weight="medium"),
            corner_radius=10,
            **kwargs
        )

class ModernCard(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Theme.BG_CARD,
            corner_radius=16,
            border_width=1,
            border_color=Theme.BORDER,
            **kwargs
        )

class DownloadItem(ModernCard):
    def __init__(self, master, title, state="idle", **kwargs):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(1, weight=1)
        
        # 아이콘 영역
        self.icon_frame = ctk.CTkFrame(self, width=60, height=60, corner_radius=12, fg_color=Theme.BG_MAIN)
        self.icon_frame.grid(row=0, column=0, rowspan=2, padx=15, pady=15)
        self.icon_frame.grid_propagate(False)
        
        self.icon_label = ctk.CTkLabel(self.icon_frame, text="󰙯", font=ctk.CTkFont(size=24), text_color=Theme.ACCENT)
        self.icon_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # 텍스트 정보
        self.title_label = ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=16, weight="bold"), 
            text_color=Theme.TEXT_PRIMARY, anchor="w"
        )
        self.title_label.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=(15, 0))
        
        self.status_label = ctk.CTkLabel(
            self, text="Ready to download", font=ctk.CTkFont(size=13), 
            text_color=Theme.TEXT_SECONDARY, anchor="w"
        )
        self.status_label.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=(0, 15))
        
        # 상태 배지
        self.badge = ctk.CTkLabel(
            self, text=state.upper(), font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=Theme.BG_MAIN, text_color=Theme.TEXT_MUTED, corner_radius=6, padx=8, pady=2
        )
        self.badge.grid(row=0, column=2, sticky="ne", padx=15, pady=15)

    def update_state(self, state, message=None, color=None):
        self.badge.configure(text=state.upper())
        if message:
            self.status_label.configure(text=message)
        if color:
            self.icon_label.configure(text_color=color)
            self.badge.configure(text_color=color)

# ====================== 메인 APP ======================

class CimeModernApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=Theme.BG_MAIN)

        self.title(f"CI.ME PRO v{APP_VERSION}")
        self.geometry("1100x750")
        self.minsize(1000, 700)

        # 로직 관련 상태
        self.queue: Queue[tuple[str, object]] = Queue()
        self.stop_event = Event()
        self.is_fetching = False
        self.is_downloading = False
        self.video_info: VideoInfo | None = None
        
        # 변수 설정
        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(self._default_download_dir()))
        self.file_name_var = tk.StringVar(value="cime_video.mp4")
        self.status_var = tk.StringVar(value="Ready to explore")
        
        self._setup_ui()
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.after(150, self._poll_queue)

    def _setup_ui(self):
        # 1. 사이드바
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=Theme.BG_SIDEBAR, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        
        # 사이드바 로고
        logo_label = ctk.CTkLabel(
            self.sidebar, text="CI.ME PRO", font=ctk.CTkFont(size=22, weight="bold"), 
            text_color=Theme.ACCENT
        )
        logo_label.pack(pady=(40, 40), padx=20)
        
        # 네비게이션 버튼
        self.btn_home = SidebarButton(self.sidebar, "Downloader", "󰓅")
        self.btn_home.configure(fg_color=Theme.BG_CARD, text_color=Theme.TEXT_PRIMARY) # Active state
        self.btn_home.pack(fill="x", padx=15, pady=5)
        
        self.btn_folder = SidebarButton(self.sidebar, "Output Folder", "󰉋", command=self.open_output_folder)
        self.btn_folder.pack(fill="x", padx=15, pady=5)
        
        self.btn_settings = SidebarButton(self.sidebar, "Settings", "󰒓", command=self._toggle_settings)
        self.btn_settings.pack(fill="x", padx=15, pady=5)
        
        # 하단 유저 정보/버전
        version_label = ctk.CTkLabel(
            self.sidebar, text=f"Version {APP_VERSION}", font=ctk.CTkFont(size=11), 
            text_color=Theme.TEXT_MUTED
        )
        version_label.pack(side="bottom", pady=20)

        # 2. 메인 컨텐츠 영역
        self.main_container = ctk.CTkFrame(self, fg_color=Theme.TRANSPARENT)
        self.main_container.pack(side="right", fill="both", expand=True, padx=40, pady=30)
        
        # 헤더
        header_frame = ctk.CTkFrame(self.main_container, fg_color=Theme.TRANSPARENT)
        header_frame.pack(fill="x", pady=(0, 20))
        
        self.greeting_label = ctk.CTkLabel(
            header_frame, text="Welcome Back", font=ctk.CTkFont(size=32, weight="bold"), 
            text_color=Theme.TEXT_PRIMARY
        )
        self.greeting_label.pack(side="left")
        
        # 3. 입력 섹션 (Glassy Input)
        self.input_card = ModernCard(self.main_container)
        self.input_card.pack(fill="x", pady=(0, 30), ipady=10)
        
        input_inner = ctk.CTkFrame(self.input_card, fg_color=Theme.TRANSPARENT)
        input_inner.pack(fill="x", padx=25, pady=20)
        
        self.url_entry = ctk.CTkEntry(
            input_inner, placeholder_text="Paste ci.me video URL here...", 
            height=54, fg_color=Theme.BG_MAIN, border_width=1, border_color=Theme.BORDER,
            corner_radius=12, font=ctk.CTkFont(size=15), textvariable=self.url_var
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        self.analyze_btn = ctk.CTkButton(
            input_inner, text="Analyze", width=140, height=54,
            fg_color=Theme.ACCENT, hover_color=Theme.ACCENT_LIGHT, corner_radius=12,
            font=ctk.CTkFont(size=15, weight="bold"), command=self.fetch_info
        )
        self.analyze_btn.pack(side="right")
        
        # 4. 설정 패널 (접이식)
        self.settings_panel = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=16, height=0)
        # 초기에는 pack 안 함
        
        # 5. 작업 리스트 영역
        list_header = ctk.CTkFrame(self.main_container, fg_color=Theme.TRANSPARENT)
        list_header.pack(fill="x", pady=(10, 10))
        
        ctk.CTkLabel(
            list_header, text="Active Task", font=ctk.CTkFont(size=18, weight="bold"), 
            text_color=Theme.TEXT_PRIMARY
        ).pack(side="left")
        
        self.task_list = ctk.CTkScrollableFrame(
            self.main_container, fg_color=Theme.TRANSPARENT, height=300
        )
        self.task_list.pack(fill="both", expand=True)
        
        self.active_task = DownloadItem(self.task_list, "No active task")
        self.active_task.pack(fill="x", pady=5)
        
        # 6. 하단 컨트롤바
        self.footer = ModernCard(self.main_container)
        self.footer.pack(fill="x", side="bottom", pady=(20, 0))
        
        footer_inner = ctk.CTkFrame(self.footer, fg_color=Theme.TRANSPARENT)
        footer_inner.pack(fill="x", padx=25, pady=15)
        
        # 진행률 표시줄
        progress_container = ctk.CTkFrame(footer_inner, fg_color=Theme.TRANSPARENT)
        progress_container.pack(side="left", fill="x", expand=True, padx=(0, 20))
        
        self.progressbar = ctk.CTkProgressBar(
            progress_container, height=10, progress_color=Theme.ACCENT, fg_color=Theme.BG_MAIN, corner_radius=5
        )
        self.progressbar.pack(fill="x", pady=(0, 5))
        self.progressbar.set(0)
        
        self.status_label = ctk.CTkLabel(
            progress_container, textvariable=self.status_var, font=ctk.CTkFont(size=12), 
            text_color=Theme.TEXT_SECONDARY, anchor="w"
        )
        self.status_label.pack(fill="x")
        
        # 컨트롤 버튼
        self.download_btn = ctk.CTkButton(
            footer_inner, text="DOWNLOAD", width=180, height=50,
            fg_color=Theme.SUCCESS, hover_color="#059669", corner_radius=12,
            font=ctk.CTkFont(size=16, weight="bold"), command=self.start_download
        )
        self.download_btn.pack(side="right")
        
        self.cancel_btn = ctk.CTkButton(
            footer_inner, text="Cancel", width=100, height=50,
            fg_color=Theme.BG_MAIN, border_width=1, border_color=Theme.BORDER,
            hover_color=Theme.BG_CARD, corner_radius=12,
            font=ctk.CTkFont(size=14), command=self.cancel_download
        )
        # 초기에는 cancel 숨김? 아니면 그냥 둠
        self.cancel_btn.pack(side="right", padx=(0, 15))

    # ====================== 토글 및 유틸 ======================
    
    def _toggle_settings(self):
        if self.settings_panel.winfo_manager():
            self.settings_panel.pack_forget()
            self.btn_settings.configure(fg_color=Theme.TRANSPARENT, text_color=Theme.TEXT_SECONDARY)
        else:
            self.settings_panel.pack(fill="x", pady=(0, 20), after=self.input_card)
            self._build_settings_content()
            self.btn_settings.configure(fg_color=Theme.BG_CARD, text_color=Theme.TEXT_PRIMARY)

    def _build_settings_content(self):
        for child in self.settings_panel.winfo_children():
            child.destroy()
            
        inner = ctk.CTkFrame(self.settings_panel, fg_color=Theme.TRANSPARENT)
        inner.pack(fill="x", padx=25, pady=20)
        
        # 저장 경로
        ctk.CTkLabel(inner, text="Save Directory", font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        path_frame = ctk.CTkFrame(inner, fg_color=Theme.TRANSPARENT)
        path_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        self.path_entry = ctk.CTkEntry(path_frame, textvariable=self.output_dir_var, height=40, fg_color=Theme.BG_MAIN, border_width=1)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(path_frame, text="Browse", width=80, height=40, fg_color=Theme.BG_MAIN, border_width=1, border_color=Theme.BORDER, command=self.choose_folder).pack(side="right")
        
        # 파일명
        ctk.CTkLabel(inner, text="File Name", font=ctk.CTkFont(size=13, weight="bold")).grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.file_entry = ctk.CTkEntry(inner, textvariable=self.file_name_var, height=40, fg_color=Theme.BG_MAIN, border_width=1)
        self.file_entry.grid(row=3, column=0, columnspan=2, sticky="ew")

    def log(self, msg):
        print(f"[*] {msg}")

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if selected:
            self.output_dir_var.set(selected)

    def open_output_folder(self) -> None:
        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    # ====================== 비즈니스 로직 ======================

    def fetch_info(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL Required", "Please enter a ci.me video URL.")
            return
        
        self.is_fetching = True
        self.analyze_btn.configure(state="disabled", text="Analyzing...")
        self.status_var.set("Fetching video metadata...")
        
        self.active_task.update_state("fetching", "Connecting to ci.me...", Theme.ACCENT)
        self.active_task.title_label.configure(text=url if len(url) < 50 else url[:47]+"...")
        
        Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str) -> None:
        try:
            info = get_video_info(url)
            self.queue.put(("info_loaded", info))
        except Exception as exc:
            self.queue.put(("task_error", exc))
        finally:
            self.queue.put(("fetch_finished", None))

    def start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            # 클립보드 확인 시도
            try:
                url = self.clipboard_get().strip()
                if "ci.me" in url:
                    self.url_var.set(url)
                else:
                    messagebox.showwarning("URL Required", "Please enter a valid ci.me URL.")
                    return
            except:
                messagebox.showwarning("URL Required", "Please enter a valid ci.me URL.")
                return

        if self.is_downloading: return

        folder = Path(self.output_dir_var.get().strip() or ".").expanduser()
        raw_name = self.file_name_var.get().strip()
        
        self.stop_event = Event()
        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="PROCESSING")
        
        self.active_task.update_state("queued", "Preparing download...", Theme.ACCENT)
        
        Thread(
            target=self._download_worker,
            args=(url, folder, raw_name),
            daemon=True,
        ).start()

    def _download_worker(self, url: str, folder: Path, raw_name: str) -> None:
        try:
            info = self.video_info if self.video_info and self.video_info.page_url == url else get_video_info(url)
            requested_name = raw_name or suggest_filename(info.title)
            output_path = build_output_path(folder, requested_name)
            
            final_path = download_with_ffmpeg(
                info.m3u8_url,
                output_path,
                progress_callback=lambda s: self.queue.put(("progress", s)),
                overwrite=True,
                stop_event=self.stop_event,
            )
            self.queue.put(("download_completed", final_path))
        except Exception as exc:
            self.queue.put(("task_error", exc))
        finally:
            self.queue.put(("download_finished", None))

    def cancel_download(self) -> None:
        if self.is_downloading:
            self.stop_event.set()
            self.status_var.set("Cancelling...")

    # ====================== 이벤트 핸들링 ======================

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
            self.video_info = info
            self.file_name_var.set(suggest_filename(info.title))
            self.active_task.title_label.configure(text=info.title or "Untitled Video")
            self.active_task.update_state("ready", "Ready to download", Theme.SUCCESS)
            self.status_var.set("Metadata loaded successfully.")
            self.greeting_label.configure(text=info.title if len(info.title) < 20 else info.title[:17]+"...")
            return

        if event == "progress":
            s = payload
            if s.state == "running":
                if s.percent:
                    self.progressbar.set(s.percent / 100)
                    self.active_task.update_state("downloading", f"Downloading... {s.percent:.1f}%", Theme.ACCENT)
                    speed = f"{s.speed_bytes_per_second/(1024*1024):.1f} MB/s" if s.speed_bytes_per_second else "-"
                    self.status_var.set(f"Speed: {speed} | Size: {s.downloaded_bytes/(1024*1024):.1f} MB")
            return

        if event == "download_completed":
            self.progressbar.set(1)
            self.active_task.update_state("completed", "Download finished!", Theme.SUCCESS)
            self.status_var.set("Task completed.")
            messagebox.showinfo("Success", f"Video saved to:\n{payload}")
            return

        if event == "task_error":
            self.active_task.update_state("error", str(payload), Theme.DANGER)
            self.status_var.set("An error occurred.")
            messagebox.showerror("Error", str(payload))
            return

        if event == "fetch_finished":
            self.is_fetching = False
            self.analyze_btn.configure(state="normal", text="Analyze")
            return

        if event == "download_finished":
            self.is_downloading = False
            self.download_btn.configure(state="normal", text="DOWNLOAD")
            return

    def _handle_close(self) -> None:
        if self.is_downloading:
            if not messagebox.askyesno("Quit", "Download is in progress. Stop and quit?"):
                return
            self.stop_event.set()
        self.destroy()

    @staticmethod
    def _default_download_dir() -> Path:
        downloads = Path.home() / "Downloads"
        return downloads if downloads.exists() else Path.cwd()

if __name__ == "__main__":
    app = CimeModernApp()
    app.mainloop()
