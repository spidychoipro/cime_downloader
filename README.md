# cime_downloader
ci.me (씨미) VOD 영상을 다운로드하는 도구

## 특징
- ci.me VOD 페이지 URL만 넣으면 자동으로 제목 가져와서 mp4로 저장
- 이미 다운로드한 파일이 있어도 강제로 삭제 후 다시 받음 (몇 번을 실행해도 새로 다운로드)
- 실시간 진행률(%) + 진행 바 + MB 단위 표시
- 한글 제목, 이모지 포함 파일명 자동 생성

## 중요 안내
- **19세 이상(성인) 영상은 다운로드가 안 될 수 있습니다.**  
  사이트 정책이나 DRM/인증 때문에 성인 콘텐츠는 정상 작동하지 않을 가능성이 큽니다.  
  일반(비성인) VOD만 테스트된 상태입니다.
- 이 도구는 개인 학습/백업 용도로만 사용하세요.  
  ci.me 이용약관 및 저작권을 반드시 준수해주세요.

## 요구 사항
- Windows 10 / 11 (64비트)
- 인터넷 연결

## 설치 방법 (클린 윈도우 기준, 5~10분 소요)

### 1. Python 설치 (필수)
1. https://www.python.org/downloads/ 접속
2. 최신 버전 (Python 3.12.x 또는 3.13.x) **Windows installer (64-bit)** 다운로드
3. 설치할 때 **반드시** 아래 두 항목 체크  
   - [x] Add python.exe to PATH  
   - [x] Install launcher for all users (recommended)
4. 설치 완료 후 PowerShell(또는 cmd) 열고 확인  
   ```powershell
   python --version
