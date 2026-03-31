from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

import requests
from bs4 import BeautifulSoup

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ci.me/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
MIN_VALID_FILE_SIZE = 100_000


class CimeDownloaderError(RuntimeError):
    """ci.me 다운로드 과정에서 발생하는 일반 오류."""


class DownloadCancelled(CimeDownloaderError):
    """사용자가 다운로드를 중단했을 때 발생."""


@dataclass(slots=True)
class VideoInfo:
    page_url: str
    title: str | None
    m3u8_url: str


@dataclass(slots=True)
class ProgressSnapshot:
    state: str
    output_path: Path
    downloaded_bytes: int = 0
    estimated_total_bytes: int | None = None
    speed_bytes_per_second: int | None = None
    percent: float | None = None
    message: str = ""


ProgressCallback = Callable[[ProgressSnapshot], None]


def sanitize_filename(title: str) -> str:
    """Windows 파일명에 쓸 수 없는 문자를 정리한다."""
    if not title:
        return "unnamed_video"

    cleaned = unicodedata.normalize("NFKC", title)
    cleaned = re.sub(r'[<>:"/\\|?*]', "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > 180:
        cleaned = cleaned[:177] + "..."

    return cleaned or "unnamed_video"


def ensure_mp4_filename(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise CimeDownloaderError("파일명을 입력해 주세요.")
    if not Path(cleaned).suffix:
        cleaned += ".mp4"
    return cleaned


def suggest_filename(title: str | None) -> str:
    if title:
        return f"{sanitize_filename(title)}.mp4"
    return "downloaded_cime_video.mp4"


def get_video_info(url: str) -> VideoInfo:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CimeDownloaderError(f"페이지 요청 실패: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    title = _extract_title(soup)
    m3u8_url = _extract_m3u8(response.text, soup)

    if not m3u8_url:
        raise CimeDownloaderError("m3u8 주소를 찾지 못했습니다.")

    return VideoInfo(page_url=url, title=title, m3u8_url=m3u8_url)


def get_title_and_m3u8(url: str) -> tuple[str | None, str | None]:
    try:
        info = get_video_info(url)
    except CimeDownloaderError:
        return None, None
    return info.title, info.m3u8_url


def download_with_ffmpeg(
    m3u8_url: str,
    output_file: str | Path,
    progress_callback: ProgressCallback | None = None,
    overwrite: bool = True,
    stop_event: Event | None = None,
) -> Path:
    output_path = Path(output_file).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("ffmpeg") is None:
        raise CimeDownloaderError("ffmpeg를 찾지 못했습니다. PATH 설정을 확인해 주세요.")

    if output_path.exists():
        if not overwrite:
            raise FileExistsError(f"파일이 이미 존재합니다: {output_path}")
        try:
            output_path.unlink()
        except PermissionError as exc:
            raise CimeDownloaderError(
                "기존 파일을 삭제할 수 없습니다. 다른 프로그램에서 사용 중인지 확인해 주세요."
            ) from exc

    cmd = [
        "ffmpeg",
        "-i",
        m3u8_url,
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-y",
        str(output_path),
    ]

    _emit(
        progress_callback,
        ProgressSnapshot(
            state="starting",
            output_path=output_path,
            message="ffmpeg를 실행하고 있습니다.",
        ),
    )

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise CimeDownloaderError(f"ffmpeg 실행 실패: {exc}") from exc

    start_time = time.time()
    last_size = 0
    estimated_total = None

    try:
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                _terminate_process(process)
                raise DownloadCancelled("사용자가 다운로드를 취소했습니다.")

            time.sleep(1)
            current_size = output_path.stat().st_size if output_path.exists() else 0
            elapsed = max(time.time() - start_time, 1)
            speed = max(current_size - last_size, 0)
            percent = None

            if elapsed > 5 and current_size > MIN_VALID_FILE_SIZE and speed > 0:
                if estimated_total is None:
                    estimated_total = int(current_size * 2.5)
                else:
                    estimated_total = max(estimated_total, current_size + speed * 60)
                percent = min((current_size / estimated_total) * 100, 99.9)

            _emit(
                progress_callback,
                ProgressSnapshot(
                    state="running",
                    output_path=output_path,
                    downloaded_bytes=current_size,
                    estimated_total_bytes=estimated_total,
                    speed_bytes_per_second=speed or None,
                    percent=percent,
                    message="다운로드 중입니다.",
                ),
            )
            last_size = current_size

        return_code = process.wait()
        final_size = output_path.stat().st_size if output_path.exists() else 0

        if return_code != 0:
            raise CimeDownloaderError("ffmpeg가 비정상 종료되었습니다.")
        if final_size <= MIN_VALID_FILE_SIZE:
            raise CimeDownloaderError("다운로드 실패 또는 파일이 거의 비어 있습니다.")

        _emit(
            progress_callback,
            ProgressSnapshot(
                state="completed",
                output_path=output_path,
                downloaded_bytes=final_size,
                estimated_total_bytes=final_size,
                speed_bytes_per_second=None,
                percent=100.0,
                message="다운로드가 완료되었습니다.",
            ),
        )
        return output_path
    except DownloadCancelled:
        _emit(
            progress_callback,
            ProgressSnapshot(
                state="cancelled",
                output_path=output_path,
                downloaded_bytes=output_path.stat().st_size if output_path.exists() else 0,
                message="다운로드가 취소되었습니다.",
            ),
        )
        raise
    except Exception:
        if process.poll() is None:
            _terminate_process(process)
        _emit(
            progress_callback,
            ProgressSnapshot(
                state="error",
                output_path=output_path,
                downloaded_bytes=output_path.stat().st_size if output_path.exists() else 0,
                message="다운로드 중 오류가 발생했습니다.",
            ),
        )
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ci.me VOD 다운로드 도구")
    parser.add_argument("url", nargs="?", help="ci.me VOD 페이지 URL")
    parser.add_argument("output_name", nargs="?", help="저장할 파일명 (생략 시 제목 자동 사용)")
    parser.add_argument(
        "--dir",
        dest="output_dir",
        default=".",
        help="저장 폴더 경로 (기본값: 현재 폴더)",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="같은 이름의 파일이 있으면 덮어쓰지 않음",
    )
    args = parser.parse_args(argv)

    if not args.url:
        parser.print_help()
        return 1

    page_url = args.url.strip()

    try:
        info = get_video_info(page_url)
        output_name = (
            ensure_mp4_filename(args.output_name)
            if args.output_name
            else suggest_filename(info.title)
        )
        output_dir = Path(args.output_dir).expanduser()
        output_path = output_dir / output_name
    except CimeDownloaderError as exc:
        print(exc)
        return 1

    print(f"대상 파일명: {output_name}")
    print(f"m3u8 주소: {info.m3u8_url}")
    if info.title:
        print(f"제목: {info.title}")
    print(f"저장 위치: {output_path}")
    print("\n다운로드 시작...\n")

    try:
        final_path = download_with_ffmpeg(
            info.m3u8_url,
            output_path,
            progress_callback=_print_cli_progress,
            overwrite=not args.keep_existing,
        )
    except FileExistsError as exc:
        print(exc)
        return 1
    except DownloadCancelled as exc:
        print(f"\n{exc}")
        return 1
    except CimeDownloaderError as exc:
        print(f"\n{exc}")
        return 1

    final_size = final_path.stat().st_size
    print(f"\n완료! -> {final_path}")
    print(f"최종 파일 크기: {final_size:,} bytes ({final_size / (1024 * 1024):.1f} MB)")
    return 0


def _extract_title(soup: BeautifulSoup) -> str | None:
    for h2_tag in soup.find_all("h2"):
        text = h2_tag.get_text(strip=True)
        if text and len(text) > 1:
            return text

    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return _strip_site_suffix(title_tag.string.strip())

    og_tag = soup.find("meta", property="og:title")
    if og_tag and og_tag.get("content"):
        return _strip_site_suffix(og_tag["content"].strip())

    return None


def _extract_m3u8(response_text: str, soup: BeautifulSoup) -> str | None:
    scripts = soup.find_all(
        "script",
        string=re.compile(r"playbackUrl|master\.m3u8", re.IGNORECASE),
    )
    pattern = r"""(https?://[^\s"'<>]+\.m3u8[^\s"'<>]*)"""

    for script in scripts:
        if script.string:
            match = re.search(pattern, script.string)
            if match:
                return match.group(1)

    match = re.search(pattern, response_text)
    if match:
        return match.group(1)

    return None


def _strip_site_suffix(text: str) -> str:
    suffix = " - 씨미"
    if text.endswith(suffix):
        return text[: -len(suffix)].strip()
    return text


def _emit(callback: ProgressCallback | None, snapshot: ProgressSnapshot) -> None:
    if callback:
        callback(snapshot)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    time.sleep(1)
    if process.poll() is None:
        process.kill()


def _format_size(value: int | None) -> str:
    if value is None:
        return "추정 중"
    return f"{value / (1024 * 1024):6.1f} MB"


def _print_cli_progress(snapshot: ProgressSnapshot) -> None:
    if snapshot.state == "starting":
        print("진행 상황 실시간 표시 중... (파일 크기 기반 추정)\n")
        return

    if snapshot.state != "running":
        return

    if snapshot.percent is None:
        line = f"\r다운로드 중... {_format_size(snapshot.downloaded_bytes)}"
        print(line, end="", flush=True)
        return

    bar_length = 30
    filled = int(bar_length * snapshot.percent / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    current_size = _format_size(snapshot.downloaded_bytes)
    total_size = _format_size(snapshot.estimated_total_bytes)
    line = f"\r진행: {snapshot.percent:6.1f}% |{bar}| {current_size} / ~{total_size}"
    print(line, end="", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
