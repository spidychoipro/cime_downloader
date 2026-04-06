# cime_downloader

ci.me(씨미) VOD 영상을 내려받는 도구입니다. `v0.3`에서는 히토미 다운로더 스타일의 큐 중심 레이아웃으로 UI를 다시 다듬고, `v0.2`에서 넣은 보안 가드를 유지했습니다.

주의:
씨미 측 정책, 저작권, 이용약관을 반드시 준수해 주세요. DRM 또는 추가 인증이 걸린 콘텐츠는 정상 동작하지 않을 수 있습니다.

## 구성

- `cime.py`: 다운로드 코어와 CLI 진입점
- `cime_gui.py`: `customtkinter` 기반 데스크톱 UI
- `cime-downloader-ui.spec`: PyInstaller 빌드 설정
- `requirements.txt`: 설치가 필요한 외부 패키지

## v0.3 변경점

- 히토미 다운로더 스크린샷 기준으로 상단 입력 바 + 메인 큐 + 하단 상태 바 구조로 재정리
- 사이드바형 대시보드 대신 더 컴팩트한 작업형 레이아웃으로 단순화
- 큐 항목 카드가 `ready`, `downloading`, `completed`, `error` 상태를 색상으로 표현
- 상단 미니 진행 바와 하단 진행 바를 함께 보여 줘 현재 상태를 한눈에 확인
- 로그 패널을 하단에 고정해 다운로드 큐 흐름을 방해하지 않도록 조정

## v0.2 변경점

- 히토미 다운로더 느낌의 다크 톤 작업형 레이아웃으로 GUI 리디자인
- URL 입력, 저장 설정, 진행률, 로그를 한 화면에 정리
- `ci.me` 호스트 이외의 URL 차단
- 리디렉션 이후 최종 페이지 URL 재검증
- 파일명에 경로 삽입 차단 및 `.mp4` 확장자 강제
- 선택한 저장 폴더 밖으로 빠져나가는 출력 경로 차단
- `ffmpeg`를 `-nostdin`으로 실행해 예기치 않은 입력 대기 방지
- `customtkinter` 데이터 파일이 포함되도록 PyInstaller 스펙 보강

## 요구 사항

- Windows 10 / 11
- Python 3.12 이상
- `ffmpeg`
- 인터넷 연결

## 설치

### 1. Python 패키지 설치

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. ffmpeg 설치

`ffmpeg`가 PATH에 있어야 합니다.

```powershell
winget install ffmpeg
```

설치 확인:

```powershell
ffmpeg -version
```

## 실행 방법

### CLI

```powershell
python cime.py "https://ci.me/@유저/vods/숫자"
python cime.py "https://ci.me/@유저/vods/숫자" "원하는이름.mp4"
python cime.py "https://ci.me/@유저/vods/숫자" --dir "C:\Users\username\Downloads"
```

### GUI

```powershell
python cime_gui.py
```

GUI에서 할 수 있는 일:

- URL 붙여넣기
- 제목 자동 감지
- 저장 폴더 선택
- 파일명 수정
- 다운로드 시작 / 취소
- 저장 폴더 바로 열기
- 로그와 진행률 확인

## EXE 빌드

```powershell
pip install pyinstaller
pyinstaller cime-downloader-ui.spec
```

빌드 결과물은 `dist\cime-downloader-ui.exe`에 생성됩니다.

## 문제 해결

### 진행률이 바로 안 뜸

초기에는 파일 크기 기반으로 추정하기 때문에 잠시 `추정 중`으로 보일 수 있습니다.

### ffmpeg를 찾지 못함

PATH 설정을 확인한 뒤 새 PowerShell 창에서 다시 실행해 주세요.

### 일부 영상이 실패함

DRM, 세션 인증, 사이트 제한 때문에 일부 콘텐츠는 다운로드되지 않을 수 있습니다.

## License

MIT License
