# E2E 시연 대시보드 실행 — 도로망 그래프 모드로 백엔드를 띄우고 브라우저를 연다.
#   실행: backend 폴더에서  powershell -ExecutionPolicy Bypass -File run_dashboard.ps1
#
# USE_ROADNET 을 .env 가 아니라 여기서만 켜는 이유: .env 는 pytest 에도 읽혀서
# 전체 테스트가 도로망 로딩(2분+)을 타고 roadnet-off 기본값 테스트가 깨진다.
# 마음 재해석(REINTERPRET_MIND) 트리거는 그래프 워커에만 있으므로 시연에는 필수.
#
# 첫 실행은 LKP 반경 3km 도로망을 Overpass 에서 내려받아 오래 걸릴 수 있다(1분 내외).
# data/roadnet_cache/ 에 캐시된 뒤로는 오프라인에서도 바로 뜬다.
# EXAONE 실호출 원문 툴팁을 보려면 .env 에 EXAONE_API_KEY 등을 채우면 된다(.env.example).

$env:USE_ROADNET = "true"
Set-Location $PSScriptRoot

$server = Start-Process -PassThru -NoNewWindow ".venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"

Write-Host "서버 시작 중... 준비되면 브라우저가 자동으로 열립니다 (첫 실행은 도로망 다운로드로 1분 내외)."
while ($true) {
    if ($server.HasExited) { throw "서버가 시작 직후 종료됐습니다 — 위 로그를 확인하세요." }
    try {
        (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/debug/overview" -TimeoutSec 2) | Out-Null
        break
    } catch { Start-Sleep -Seconds 2 }
}
Start-Process "http://127.0.0.1:8000/dashboard"
Wait-Process -Id $server.Id
