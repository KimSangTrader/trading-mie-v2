<#
.SYNOPSIS
  sync_krx_to_ec2.ps1을 Windows 작업 스케줄러에 반복 작업으로 1회 등록한다.

.DESCRIPTION
  평일(월~금) 15:00부터 20:00까지, 10분 간격으로 sync_krx_to_ec2.ps1을 실행하도록
  등록한다. EC2의 mie-v2-valuation.timer가 18:00 KST에 도는 것보다 여유있게
  앞뒤로 커버하는 창(15:00~20:00)이다 - 필요하면 아래 $StartTime/$DurationHours를
  조정할 것.

  주의: 이 작업은 "이 Windows PC가 그 시간에 켜져 있고 로그온돼 있을 때"만
  실행된다 - EC2의 systemd 타이머와 달리 PC 전원 상태에 의존한다. KRX
  CSV 다운로드 자체가 사람 손을 타는 이상(안티봇 조치로 자동화 불가)
  이 단계는 원래도 사람이 그 시간대에 PC를 쓰고 있어야 하므로 특별히
  새로운 제약은 아니다.

  PowerShell을 관리자 권한으로 실행한 뒤 이 스크립트를 1회만 실행하면 된다.
#>

$TaskName    = "MIE-V2-KRX-Sync"
$ScriptPath  = "C:\Projects\trading-mie-v2\scripts\windows\sync_krx_to_ec2.ps1"
$StartTime   = "15:00"
$DurationHours = 5   # 15:00 ~ 20:00
$IntervalMin = 10

if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ 스크립트를 찾을 수 없습니다: $ScriptPath - 경로를 확인해주세요." -ForegroundColor Red
    exit 1
}

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $StartTime
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMin) `
    -RepetitionDuration (New-TimeSpan -Hours $DurationHours)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "MIE V2.0 - 로컬 data/krx/incoming/의 KRX CSV를 EC2로 자동 scp 전송 (Phase 5-22)" `
    -Force

Write-Host "✅ 작업 스케줄러 등록 완료: $TaskName (평일 $StartTime 부터 ${DurationHours}시간 동안 ${IntervalMin}분 간격)"
Write-Host "   작업 스케줄러 GUI에서 '$TaskName'을 검색하면 확인/수정할 수 있습니다."
Write-Host "   지금 바로 1회 테스트하려면: Start-ScheduledTask -TaskName '$TaskName'"
