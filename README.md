# cime_downloader

ci.me(씨미) VOD 영상을 내려받는 도구입니다. `v0.4`에서는 **Nebula Modern UI**로 전면 개편하여, 단순한 도구를 넘어선 프리미엄 앱 경험을 제공합니다.

## 구성

- `cime.py`: 다운로드 코어와 CLI 진입점
- `cime_gui.py`: `customtkinter` 기반의 현대적인 Nebula UI
- `cime-downloader-ui.spec`: PyInstaller 빌드 설정
- `requirements.txt`: 설치가 필요한 외부 패키지

## v0.4.0 Nebula Release (New!)

- **완전 아주 모던한 디자인**: 심해의 어둠을 형상화한 Nebula 테마와 반투명 카드 레이아웃 적용
- **사이드바 내비게이션**: 직관적인 사이드바를 통해 다운로더, 설정, 출력 폴더에 빠르게 접근
- **지능형 분석**: URL 입력 시 메타데이터를 즉시 분석하여 제목과 예상 파일명을 표시
- **강화된 시각화**: 작업 상태별 아이콘과 색상 변화, 부드러운 진행률 표시로 작업 상태를 한눈에 파악
- **설정 패널**: 복잡한 설정(경로, 파일명)을 필요할 때만 열어볼 수 있는 슬라이딩 패널 구조

## v0.3 ~ v0.1

- 초기 CLI 버전 및 기초적인 GUI(4K Video Downloader 스타일) 구현
- 보안 가드(호스트 검증, 경로 탈출 방지 등) 도입
- `ffmpeg` 연동 및 진행률 추정 로직 최적화

## 설치 및 요구 사항

- **OS**: Windows 10 / 11
- **Python**: 3.12 이상
- **외부 도구**: `ffmpeg` (PATH 등록 필수)

```powershell
# 패키지 설치
pip install -r requirements.txt

# ffmpeg 설치 (winget 사용 시)
winget install ffmpeg
```

## 사용 방법

### GUI (추천)
```powershell
python cime_gui.py
```
- URL을 붙여넣고 **Analyze**를 누르면 영상 정보를 가져옵니다.
- **DOWNLOAD**를 눌러 즉시 저장을 시작하세요.

### CLI
```powershell
python cime.py "https://ci.me/@user/vods/123"
```

## 빌드 (EXE 제작)
```powershell
pyinstaller cime-downloader-ui.spec
```

## License
MIT License
