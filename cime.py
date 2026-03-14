import re
import sys
import subprocess
import requests
import os
import time
from bs4 import BeautifulSoup
import unicodedata
from threading import Thread

def sanitize_filename(title: str) -> str:
    """파일명 정리"""
    if not title:
        return "unnamed_video"
    title = unicodedata.normalize('NFKC', title)
    invalid_chars = r'[<>:"/\\|?*]'
    title = re.sub(invalid_chars, '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) > 180:
        title = title[:177] + "..."
    return title


def get_title_and_m3u8(url: str) -> tuple[str | None, str | None]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://ci.me/",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"페이지 요청 실패: {e}")
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")

    title = None
    h2_tags = soup.find_all("h2")
    for h2 in h2_tags:
        text = h2.get_text(strip=True)
        if text and len(text) > 1:
            title = text
            break

    if not title:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title_text = title_tag.string.strip()
            if title_text.endswith(" - 씨미"):
                title = title_text[:-6].strip()
            else:
                title = title_text

    if not title:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title_text = og["content"].strip()
            if title_text.endswith(" - 씨미"):
                title = title_text[:-6].strip()
            else:
                title = title_text

    m3u8 = None
    scripts = soup.find_all("script", string=re.compile(r"playbackUrl|master\.m3u8", re.IGNORECASE))
    for script in scripts:
        if script.string:
            m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', script.string)
            if m:
                m3u8 = m.group(1)
                break

    if not m3u8:
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', resp.text)
        if m:
            m3u8 = m.group(1)

    return title, m3u8


def download_with_ffmpeg(m3u8_url: str, output_file: str):
    cmd = [
        "ffmpeg",
        "-i", m3u8_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-y",
        output_file
    ]

    print("\n다운로드 시작...")
    print("명령어 :", " ".join(cmd[:5]) + " ...")
    print("저장 위치 :", output_file)
    print("진행 상황 실시간 표시 중... (파일 크기 기반 추정)\n")

    # ffmpeg 백그라운드 실행 (로그 무시)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # 진행률 추정용 변수
    start_time = time.time()
    last_size = 0
    estimated_total = None
    bar_length = 30

    try:
        while process.poll() is None:
            time.sleep(1)  # 1초마다 체크

            if os.path.exists(output_file):
                current_size = os.path.getsize(output_file)
            else:
                current_size = 0

            elapsed = time.time() - start_time

            # 5초 이후부터 추정 시작
            if elapsed > 5 and current_size > 100000:
                speed = (current_size - last_size)  # bytes/sec
                if speed > 0:
                    if not estimated_total:
                        # 처음 추정: 현재 속도로 2배 가정 (조정됨)
                        estimated_total = current_size * 2.5
                    else:
                        # 속도 기반으로 총 크기 업데이트
                        remaining_estimate = speed * 60  # 최소 60초 남음 가정
                        estimated_total = max(estimated_total, current_size + remaining_estimate)

                    percent = (current_size / estimated_total) * 100
                    percent = min(percent, 99.9)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    size_mb = current_size / (1024 * 1024)
                    est_total_mb = estimated_total / (1024 * 1024)

                    print(f"\r진행: {percent:6.1f}% |{bar}| {size_mb:6.1f} MB / ~{est_total_mb:6.1f} MB", end="", flush=True)

                last_size = current_size

        process.wait()
        print("\n" + " " * 100)  # 클리어

        final_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        if final_size > 100000:
            print(f"\n완료! → {output_file}")
            print(f"최종 파일 크기: {final_size:,} bytes ({final_size / (1024*1024):.1f} MB)")
        else:
            print("\n다운로드 실패 또는 파일이 거의 비어있습니다.")

    except KeyboardInterrupt:
        print("\n사용자 중단 (Ctrl+C) → ffmpeg 종료")
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
    except Exception as e:
        print(f"\n오류 발생: {e}")
        if process.poll() is None:
            process.terminate()


def main():
    if len(sys.argv) < 2:
        print("사용법:")
        print("  python cime.py https://ci.me/@유저/vods/숫자")
        print("  python cime.py https://ci.me/@유저/vods/숫자 원하는파일명.mp4")
        sys.exit(1)

    page_url = sys.argv[1].strip()

    if len(sys.argv) >= 3:
        output_name = sys.argv[2].strip()
    else:
        title, _ = get_title_and_m3u8(page_url)
        if title:
            safe_title = sanitize_filename(title)
            output_name = f"{safe_title}.mp4"
        else:
            output_name = "downloaded_cime_video.mp4"

    print(f"대상 파일명: {output_name}")

    # 파일이 있으면 무조건 삭제 (몇 번을 해도 다시 받게)
    if os.path.exists(output_name):
        print(f"기존 파일 발견 → 강제 삭제합니다: {output_name}")
        try:
            os.remove(output_name)
            print("삭제 완료 → 새로 다운로드 시작")
        except PermissionError:
            print("파일 삭제 실패: 권한 없음 (다른 프로그램에서 사용 중이거나 읽기 전용)")
            print("직접 삭제하거나 다른 파일명으로 실행하세요.")
        except Exception as e:
            print(f"파일 삭제 실패: {e}")
            print("직접 삭제 후 다시 실행하세요.")

    title, m3u8 = get_title_and_m3u8(page_url)
    if not m3u8:
        print("m3u8 주소를 찾지 못했습니다.")
        sys.exit(1)

    print(f"m3u8 주소: {m3u8}")
    if title:
        print(f"제목: {title}")

    print(f"\n다운로드 시작 → {output_name}\n")

    download_with_ffmpeg(m3u8, output_name)


if __name__ == "__main__":
    main()
