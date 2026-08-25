<#
.SYNOPSIS
  data/krx/incoming/ 로컬(Windows) 폴더에 있는 KRX CSV를 EC2의
  /opt/mie-v2/data/krx/incoming/ 로 자동 전송한다 (Phase 5-22).

.DESCRIPTION
  KRX 사이트 자체 다운로드는 여전히 사람이 해야 한다(안티봇 조치로 자동화
  불가 - Phase 5-8 결정 그대로 유지). 이 스크립트는 그 다음 단계, 즉
  "다운로드한 파일을 EC2로 옮기는 것"만 자동화한다. 사람이 이 로컬
  incoming/ 폴더에 파일을 떨어뜨려 놓기만 하면, Windows 작업 스케줄러가
  이 스크립트를 주기적으로 실행해 EC2로 scp 전송하고, 성공한 파일은
  incoming/_sent/ 로 옮겨서 같은 파일을 중복 전송하지 않는다.
  EC2 쪽은 이미 mie-v2-krx-import.timer(15분 간격)가 떠있어서, 도착한 CSV를
  알아서 검증·반영한다 - 이 스크립트는 딱 "파일 옮기기"까지만 책임진다.

  전제: Windows에 OpenSSH 클라이언트(scp.exe/ssh.exe, Windows 10 1803+
  기본 포함)가 설치돼 있어야 한다. PowerShell에서 `scp` 명령이 되는지
  먼저 확인해볼 것.

.NOTES
  아래 설정값 4개(Ec2Host/Ec2User/SshKeyPath 및 필요시 경로)를 실제 값으로
  바꾼 뒤 사용할 것 - 이 저장소에는 자리표시자만 커밋되어 있다(민감정보 아님,
  단지 사용자 환경마다 달라서).
#>

# ============ 설정 (사용자 환경에 맞게 수정) ============
$Ec2Host        = "3.37.131.112"                          # 예: 13.125.xxx.xxx 또는 ec2-xxx.compute.amazonaws.com
$Ec2User        = "ubuntu"
$SshKeyPath     = "C:\secureKey\mie-v2-key.pem"   # SSH 접속에 쓰시던 그 키 파일 경로
$RemoteIncoming = "/opt/mie-v2/data/krx/incoming/"
# ========================================================

$LocalIncoming = "C:\Projects\trading-mie-v2\data\krx\incoming"
$SentDir       = Join-Path $LocalIncoming "_sent"
$LogDir        = "C:\Projects\trading-mie-v2\logs"
$LogFile       = Join-Path $LogDir "krx_sync.log"

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
if (-not (Test-Path $SentDir)) { New-Item -ItemType Directory -Path $SentDir -Force | Out-Null }

if ($Ec2Host -eq "REPLACE_ME" -or $SshKeyPath -like "REPLACE_ME") {
    Write-Log "❌ 설정값(Ec2Host/SshKeyPath)이 아직 자리표시자입니다 - 스크립트 상단을 실제 값으로 바꿔주세요. 중단."
    exit 1
}

if (-not (Test-Path $LocalIncoming)) {
    Write-Log "❌ 로컬 incoming 폴더가 없습니다: $LocalIncoming"
    exit 1
}

# kospi/kosdaq이 파일명에 들어간 .csv만 대상으로 한다 (최종 검증은 EC2의
# krx_importer.py가 하므로, 여기서는 엉뚱한 파일을 안 보내는 정도의 가벼운
# 필터만 둔다). 다운로드가 아직 끝나지 않은 파일(브라우저가 쓰는 중)을
# 잘못 집지 않도록, 마지막 수정 시각이 30초 이상 지난 파일만 대상으로 한다.
$cutoff = (Get-Date).AddSeconds(-30)
$targets = Get-ChildItem -Path $LocalIncoming -Filter "*.csv" -File |
    Where-Object { $_.Name -match "(?i)kospi|kosdaq" -and $_.LastWriteTime -lt $cutoff }

if ($targets.Count -eq 0) {
    Write-Log "전송할 새 CSV 없음 (local incoming/ 비어있거나 이미 다 보냄)"
    exit 0
}

foreach ($file in $targets) {
    Write-Log "전송 시도: $($file.Name)"
    $scpArgs = @("-i", $SshKeyPath, "-o", "StrictHostKeyChecking=no", $file.FullName, "${Ec2User}@${Ec2Host}:${RemoteIncoming}")
    $proc = Start-Process -FilePath "scp" -ArgumentList $scpArgs -NoNewWindow -Wait -PassThru `
        -RedirectStandardError (Join-Path $LogDir "scp_stderr.tmp")

    if ($proc.ExitCode -eq 0) {
        $destPath = Join-Path $SentDir $file.Name
        Move-Item -Path $file.FullName -Destination $destPath -Force
        Write-Log "✅ 전송 성공, _sent/로 이동: $($file.Name) (EC2 mie-v2-krx-import.timer가 15분 내 자동 반영)"
    } else {
        $stderrContent = Get-Content (Join-Path $LogDir "scp_stderr.tmp") -Raw -ErrorAction SilentlyContinue
        Write-Log "⚠️  전송 실패(exit $($proc.ExitCode)): $($file.Name) - $stderrContent - 다음 실행 때 재시도합니다 (파일을 지우지 않음)"
    }
}

Remove-Item (Join-Path $LogDir "scp_stderr.tmp") -ErrorAction SilentlyContinue