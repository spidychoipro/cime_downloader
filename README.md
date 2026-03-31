# cime_downloader

ci.me(씨미) VOD 영상을 내려받는 도구입니다.  
기존 CLI 스크립트에 더해, 4K Video Downloader처럼 바로 쓸 수 있는 데스크톱 UI 버전도 포함했습니다.

※ 씨미 측 정책, 저작권, 이용약관을 반드시 준수해 주세요. DRM 또는 추가 인증이 걸린 콘텐츠는 정상 동작하지 않을 수 있습니다. ※

## 구성

- `cime.py`: 기존 명령줄 다운로드 도구
- `cime_gui.py`: Tkinter 기반 데스크톱 UI
- `requirements.txt`: 설치가 필요한 외부 패키지

## 주요 기능

- ci.me VOD URL만 넣으면 제목을 감지해 파일명을 자동 제안
- `ffmpeg`로 HLS(m3u8) 스트림을 mp4로 저장
- 기존 파일 자동 덮어쓰기 옵션
- 진행률, 예상 용량, 속도, 로그를 UI에서 확인
- CLI와 GUI가 같은 다운로드 코어를 함께 사용

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

설치 뒤 확인:

```powershell
ffmpeg -version
```

## 실행 방법

### CLI

기존처럼 그대로 사용할 수 있습니다.

```powershell
python cime.py "https://ci.me/@유저/vods/숫자"
python cime.py "https://ci.me/@유저/vods/숫자" "원하는이름.mp4"
python cime.py "https://ci.me/@유저/vods/숫자" --dir "C:\Users\username\Downloads"
```

### GUI

데스크톱 앱처럼 실행하려면:

```powershell
python cime_gui.py
```

앱에서 할 수 있는 일:

- URL 붙여넣기
- 제목 자동 불러오기
- 저장 폴더 선택
- 파일명 수정
- 다운로드 시작 / 취소
- 저장 폴더 바로 열기

## EXE로 만들기

원하면 추후 `pyinstaller`로 GUI 실행 파일도 만들 수 있습니다.

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile cime_gui.py --name cime-downloader-ui
```

빌드 결과물은 `dist\cime-downloader-ui.exe`에 생성됩니다.

## 문제 해결

### 진행률이 바로 안 뜸

초기에는 파일 크기 기반으로 추정하기 때문에 잠시 `추정 중`으로 보일 수 있습니다.

### ffmpeg를 찾지 못함

PATH 설정을 확인한 뒤 새 PowerShell 창에서 다시 실행해 주세요.

### 성인 영상 / 특정 영상이 실패함

DRM, 세션 인증, 사이트 제한 때문에 일부 콘텐츠는 다운로드되지 않을 수 있습니다.

## License

MIT License
