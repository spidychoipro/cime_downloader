# cime_downloader

ci.me (씨미) VOD 영상을 다운로드하는 도구

※ 씨미 측에서 문제 제기하면 이도구는 사라질수 있음을 안내 합니다. ※

## 특징

* ci.me VOD 페이지 URL만 넣으면 자동으로 제목을 가져와 mp4로 저장
* 이미 다운로드한 파일이 있어도 **강제로 삭제 후 다시 다운로드**
* 실시간 진행률(%) + 진행 바 + MB 단위 표시
* 한글 제목 및 이모지 파일명 지원

## 중요 안내

* **19세 이상 영상은 다운로드가 안 될 수 있습니다.**
* DRM 또는 사이트 인증 때문에 성인 콘텐츠는 정상 작동하지 않을 수 있습니다.
* 일반 VOD 기준으로 테스트되었습니다.

이 도구는 개인 백업 및 학습 용도로만 사용하세요.
ci.me 이용약관과 저작권을 반드시 준수해야 합니다.

---

# 요구 사항

* Windows 10 / 11 (64bit)
* Python 3.12 이상
* ffmpeg
* 인터넷 연결

---

# 설치 방법 (클린 윈도우 기준)

## 1. Python 설치

1. https://www.python.org/downloads/ 접속
2. 최신 버전 **Windows installer (64-bit)** 다운로드
3. 설치 시 반드시 아래 옵션 체크

```
[x] Add python.exe to PATH
[x] Install launcher for all users
```

4. 설치 확인

```powershell
python --version
```

정상 출력 예시

```
Python 3.12.x
```

---

## 2. Python 패키지 설치

PowerShell에서 실행

```powershell
python -m pip install --upgrade pip
pip install requests beautifulsoup4
```

---

## 3. ffmpeg 설치

ci.me 영상은 **HLS(m3u8)** 형식이라 ffmpeg가 필요합니다.

### 다운로드

https://www.gyan.dev/ffmpeg/builds/

또는 
```
winget install ffmpeg
```

다음 파일 다운로드

```
ffmpeg-release-essentials.zip
```

### 설치

압축 해제 후 폴더를 원하는 위치에 이동

예시

```
C:\ffmpeg
```

폴더 안에 다음 파일이 있어야 합니다.

```
ffmpeg.exe
ffprobe.exe
ffplay.exe
```

---

### 환경 변수 설정

1. Windows 검색 → **환경 변수 편집**
2. **시스템 환경 변수 편집**
3. **환경 변수**
4. 시스템 변수 → **Path**
5. **편집 → 새로 만들기**

```
C:\ffmpeg\bin
```

6. 확인 → 확인

---

### 설치 확인

PowerShell 새로 열고 실행

```powershell
ffmpeg -version
```

정상 출력 예시

```
ffmpeg version 6.x ...
```

---

# 사용 방법

## 1. 스크립트 준비

`cime.py` 파일을 다운로드하거나 같은 폴더에 저장

예시 위치

```
C:\Users\username\Downloads
```

---

## 2. PowerShell에서 폴더 이동

```powershell
cd C:\Users\username\Downloads
```

---

## 3. 다운로드 실행

기본 실행

```powershell
python cime.py "https://ci.me/@유저/vods/숫자"
```

파일 이름 지정

```powershell
python cime.py "https://ci.me/@유저/vods/숫자" "원하는이름.mp4"
```

---

# 실행 예시

```
대상 파일명: 테스트 첫방송인데 오팬무요.. 🎃.mp4
기존 파일 발견 → 강제 삭제합니다...
삭제 완료 → 새로 다운로드 시작

m3u8 주소: https://streaming.cf.ci.me/...
제목: 테스트 첫방송인데 오팬무요..? 🎃

다운로드 시작...

진행: 45.2% |██████████████░░░░░░░░░░░░| 168.7 MB / ~373.0 MB

완료 → 테스트 첫방송인데 오팬무요.. 🎃.mp4
최종 파일 크기: 373.2 MB
```

---

# 문제 해결

## 진행률이 표시되지 않음

처음 몇 초 동안은 파일 크기 추정이 불가능할 수 있습니다.
조금 기다리면 정상적으로 표시됩니다.

## ffmpeg가 인식되지 않음

환경 변수 Path에 다음 경로가 포함되어 있는지 확인

```
C:\ffmpeg\bin
```

PowerShell을 다시 열어야 적용됩니다.

## 다운로드된 파일이 깨짐

네트워크 문제일 수 있습니다.
다시 실행하면 자동으로 삭제 후 재다운로드됩니다.

## 성인 영상 다운로드 실패

성인 콘텐츠는 DRM 또는 인증 때문에 다운로드가 차단될 수 있습니다.

---

# License

MIT License

자유롭게 사용 및 수정 가능
단, ci.me 이용약관과 저작권법을 준수해야 합니다.

---

# Author

옴걸 타임즈 (2026)

GitHub Issues 또는 DM으로 문의 가능
