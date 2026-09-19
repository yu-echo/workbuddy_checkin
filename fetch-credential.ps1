# WorkBuddy 凭证获取脚本
#
# 读取本机 WorkBuddy 的登录态，拼出 `手机号:accessToken:refreshToken`
# 并复制到剪贴板，供配置 GitHub Secret 使用。
#
# 用法一（推荐，一行命令）：
#   irm https://raw.githubusercontent.com/yu-echo/workbuddy_checkin/main/fetch-credential.ps1 | iex
#
# 用法二（本地运行）：
#   powershell -ExecutionPolicy Bypass -File fetch-credential.ps1
#
# 说明：
#   - 脚本不会打印凭据明文，只显示脱敏手机号与令牌长度，避免截图/录屏泄露。
#   - 需要在已登录 WorkBuddy 的机器上运行。

$ErrorActionPreference = 'SilentlyContinue'

$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info'),
    (Join-Path $env:APPDATA      'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info')
)

$file = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $file) {
    Write-Host ''
    Write-Host '[ERROR] 未找到 WorkBuddy 登录态文件。' -ForegroundColor Red
    Write-Host '        请确认本机已安装并登录 WorkBuddy，然后重新运行。' -ForegroundColor Yellow
    Write-Host '        查找过以下位置：' -ForegroundColor DarkGray
    $candidates | ForEach-Object { Write-Host ('          ' + $_) -ForegroundColor DarkGray }
    Write-Host ''
    return
}

$data = Get-Content -Raw -Encoding UTF8 $file | ConvertFrom-Json

if (-not $data) {
    Write-Host ''
    Write-Host '[ERROR] 登录态文件不是合法 JSON，可能已损坏或版本不兼容。' -ForegroundColor Red
    Write-Host ('        文件：' + $file) -ForegroundColor DarkGray
    Write-Host ''
    return
}

$phone = $data.account.phoneNumber
$at    = $data.auth.accessToken
$rt    = $data.auth.refreshToken

$missing = @()
if (-not $phone) { $missing += 'account.phoneNumber' }
if (-not $at)    { $missing += 'auth.accessToken' }
if (-not $rt)    { $missing += 'auth.refreshToken' }

if ($missing.Count -gt 0) {
    Write-Host ''
    Write-Host ('[ERROR] 登录态缺少字段：' + ($missing -join ', ')) -ForegroundColor Red
    Write-Host '        若你是用邮箱登录的 WorkBuddy，签到脚本仍要求 手机号:AT:RT 格式，' -ForegroundColor Yellow
    Write-Host '        请改用绑定手机号的账号登录后再试。' -ForegroundColor Yellow
    Write-Host ''
    return
}

# 拼装并复制
Set-Clipboard -Value ($phone + ':' + $at + ':' + $rt)

if ($phone.Length -ge 7) {
    $mask = $phone.Substring(0, 3) + '****' + $phone.Substring($phone.Length - 4)
} else {
    $mask = '***'
}

Write-Host ''
Write-Host '[OK] 凭证已复制到剪贴板（出于安全考虑不在此处显示明文）' -ForegroundColor Green
Write-Host ('     手机号        : ' + $mask)
Write-Host ('     accessToken  : ' + $at.Length + ' 字符')
Write-Host ('     refreshToken : ' + $rt.Length + ' 字符')

if ($data.auth.refreshExpiresAt) {
    $exp  = [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$data.auth.refreshExpiresAt).LocalDateTime
    $days = [math]::Floor(($exp - (Get-Date)).TotalDays)
    Write-Host ('     凭证有效期至 : ' + $exp.ToString('yyyy-MM-dd') + '  (剩余 ' + $days + ' 天)') -ForegroundColor Cyan
}

Write-Host ''
Write-Host '接下来：' -ForegroundColor Green
Write-Host '  1. 打开你的仓库 -> Settings -> Secrets and variables -> Actions'
Write-Host '  2. New repository secret'
Write-Host '  3. Name 填 WORKBUDDY_REFRESH_TOKEN，Secret 粘贴剪贴板内容'
Write-Host '  4. 到 Actions 页面手动触发一次 WorkBuddy 自动签到'
Write-Host ''
