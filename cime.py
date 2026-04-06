from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

APP_VERSION = "0.2.0"
SUPPORTED_PAGE_HOSTS = frozenset({"ci.me", "www.ci.me"})
SUPPORTED_SCHEMES = frozenset({"http", "https"})
WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)
REQUEST_TIMEOUT_SECONDS = 15
MIN_VALID_FILE_SIZE = 100_000
INVALID_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*]')

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ci.me/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


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
    cleaned = "".join(character for character in cleaned if ord(character) >= 32)
    cleaned = INVALID_FILENAME_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")

    if len(cleaned) > 180:
        cleaned = cleaned[:177].rstrip(" .") + "..."

    if not cleaned:
        return "unnamed_video"

    if _is_reserved_windows_name(cleaned):
        return f"{cleaned}_video"

    return cleaned


def ensure_mp4_filename(name: str) -> str:
    cleaned = unicodedata.normalize("NFKC", name.strip())
    if not cleaned:
        raise CimeDownloaderError("파일명을 입력해 주세요.")
    if any(ord(character) < 32 for character in cleaned):
        raise CimeDownloaderError("파일명에 제어 문자를 넣을 수 없습니다.")
    if Path(cleaned).name != cleaned or "/" in cleaned or "\\" in cleaned:
        raise CimeDownloaderError("파일명에는 폴더 경로를 넣을 수 없습니다.")
    if INVALID_FILENAME_PATTERN.search(cleaned):
        raise CimeDownloaderError("파일명에 사용할 수 없는 문자가 포함되어 있습니다.")

    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        raise CimeDownloaderError("파일명이 올바르지 않습니다.")

    suffix = Path(cleaned).suffix.lower()
    if not suffix:
        cleaned = f"{cleaned}.mp4"
    elif suffix != ".mp4":
        cleaned = f"{Path(cleaned).stem}.mp4"

    if _is_reserved_windows_name(cleaned):
        raise CimeDownloaderError("Windows 예약어는 파일명으로 사용할 수 없습니다.")

    return cleaned


def suggest_filename(title: str | None) -> str:
    if title:
        return f"{sanitize_filename(title)}.mp4"
    return "downloaded_cime_video.mp4"


def validate_page_url(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        raise CimeDownloaderError("ci.me VOD URL을 입력해 주세요.")

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES or not parsed.netloc:
        raise CimeDownloaderError("http/https 형식의 ci.me URL만 지원합니다.")

    host = (parsed.hostname or "").lower()
    if host not in SUPPORTED_PAGE_HOSTS:
        raise CimeDownloaderError("ci.me VOD 페이지 URL만 지원합니다.")

    if "/vods/" not in parsed.path:
        raise CimeDownloaderError("ci.me VOD 상세 페이지 URL만 지원합니다.")

    return urlunparse(parsed._replace(fragment=""))


def build_output_path(output_dir: str | Path, output_name: str) -> Path:
    directory = Path(output_dir).expanduser()
    if directory.exists() and not directory.is_dir():
        raise CimeDownloaderError("저장 위치가 폴더가 아닙니다.")

    safe_name = ensure_mp4_filename(output_name)
    output_path = directory / safe_name

    resolved_directory = directory.resolve(strict=False)
    resolved_output = output_path.resolve(strict=False)
    if resolved_output.parent != resolved_directory:
        raise CimeDownloaderError("저장 경로가 선택한 폴더 밖으로 벗어날 수 없습니다.")

    return output_path


def get_video_info(url: str) -> VideoInfo:
    page_url = validate_page_url(url)

    try:
        response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CimeDownloaderError(f"페이지 요청 실패: {exc}") from exc

    final_page_url = _validate_final_page_url(response.url)
    soup = BeautifulSoup(response.text, "html.parser")
    title = _extract_title(soup)
    m3u8_url = _extract_m3u8(response.text, soup, final_page_url)

    if not m3u8_url:
        raise CimeDownloaderError("m3u8 주소를 찾지 못했습니다.")

    return VideoInfo(page_url=final_page_url, title=title, m3u8_url=m3u8_url)


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
    if output_path.suffix.lower() != ".mp4":
        raise CimeDownloaderError("출력 파일은 mp4 형식만 지원합니다.")

    if shutil.which("ffmpeg") is None:
        raise CimeDownloaderError("ffmpeg를 찾지 못했습니다. PATH 설정을 확인해 주세요.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        if output_path.is_dir():
            raise CimeDownloaderError("출력 경로가 폴더와 충돌합니다.")
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
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
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
            message="ffmpeg를 안전 모드로 실행하고 있습니다.",
        ),
    )

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
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
                _cleanup_cancelled_output(output_path)
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
        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read().strip()

        final_size = output_path.stat().st_size if output_path.exists() else 0

        if return_code != 0:
            detail = f" ({stderr_output.splitlines()[-1]})" if stderr_output else ""
            raise CimeDownloaderError(f"ffmpeg가 비정상 종료되었습니다.{detail}")
        if final_size <= MIN_VALID_FILE_SIZE:
            _cleanup_cancelled_output(output_path)
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
                downloaded_bytes=0,
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

    try:
        info = get_video_info(args.url)
        output_name = ensure_mp4_filename(args.output_name) if args.output_name else suggest_filename(info.title)
        output_path = build_output_path(args.output_dir, output_name)
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


def _extract_m3u8(response_text: str, soup: BeautifulSoup, base_url: str) -> str | None:
    pattern = r"""(https?://[^\s"'<>]+\.m3u8[^\s"'<>]*)"""
    scripts = soup.find_all(
        "script",
        string=re.compile(r"playbackUrl|master\.m3u8", re.IGNORECASE),
    )

    for source_text in [_decode_escaped_text(script.string) for script in scripts if script.string]:
        match = re.search(pattern, source_text)
        if match:
            media_url = _validate_media_url(match.group(1), base_url)
            if media_url:
                return media_url

    normalized_response = _decode_escaped_text(response_text)
    match = re.search(pattern, normalized_response)
    if match:
        media_url = _validate_media_url(match.group(1), base_url)
        if media_url:
            return media_url

    return None


def _validate_final_page_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES or host not in SUPPORTED_PAGE_HOSTS:
        raise CimeDownloaderError("지원되지 않는 페이지로 리디렉션되었습니다.")
    if "/vods/" not in parsed.path:
        raise CimeDownloaderError("VOD 상세 페이지 확인에 실패했습니다.")
    return urlunparse(parsed._replace(fragment=""))


def _validate_media_url(url: str, base_url: str) -> str | None:
    candidate = urljoin(base_url, url.strip())
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES or not parsed.netloc:
        return None
    if not parsed.path.lower().endswith(".m3u8"):
        return None
    return urlunparse(parsed._replace(fragment=""))


def _decode_escaped_text(value: str) -> str:
    decoded = value.replace("\\/", "/").replace("\\u0026", "&")
    return html.unescape(decoded)


def _is_reserved_windows_name(name: str) -> bool:
    stem = Path(name).stem.rstrip(" .").upper()
    return stem in WINDOWS_RESERVED_NAMES


def _strip_site_suffix(text: str) -> str:
    suffix = " - 씨미"
    if text.endswith(suffix):
        return text[: -len(suffix)].strip()
    return text


def _emit(callback: ProgressCallback | None, snapshot: ProgressSnapshot) -> None:
    if callback:
        callback(snapshot)


def _terminate_process(process: subprocess.Popen[object]) -> None:
    process.terminate()
    time.sleep(1)
    if process.poll() is None:
        process.kill()


def _cleanup_cancelled_output(output_path: Path) -> None:
    try:
        if output_path.exists() and output_path.stat().st_size < MIN_VALID_FILE_SIZE:
            output_path.unlink()
    except OSError:
        return


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
