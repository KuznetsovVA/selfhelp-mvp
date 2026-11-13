# Публичный доступ к серверу без VPN.
#
# Вариант А (нужен установленный cloudflared):
#   cloudflared tunnel --url http://localhost:8000
#
# Вариант Б (ничего устанавливать не нужно, встроенный OpenSSH):
#   .\start-tunnel.ps1
#
# Оба варианта публикуют локальный порт 8000 в интернет на время работы процесса.

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cf) {
    Write-Host "Найден cloudflared, запускаю туннель:" -ForegroundColor Green
    & cloudflared tunnel --url "http://localhost:$Port"
    exit
}

Write-Host "cloudflared не установлен — использую встроенный SSH-туннель." -ForegroundColor Yellow
Write-Host "Для варианта с cloudflared: winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
Write-Host ""

$ssh = Join-Path $env:SystemRoot "System32\OpenSSH\ssh.exe"
if (-not (Test-Path -LiteralPath $ssh)) {
    Write-Host "OpenSSH не найден. Включите: Параметры -> Приложения -> Дополнительные компоненты -> Клиент OpenSSH." -ForegroundColor Red
    exit 1
}

try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5
    Write-Host "Локальный сервер на порту $Port отвечает." -ForegroundColor Green
} catch {
    Write-Host "Сервер на порту $Port не отвечает. Сначала запустите: python server.py" -ForegroundColor Red
    exit 1
}

Write-Host "Открываю туннель. Ссылка появится ниже (строки с https://...lhr.life)" -ForegroundColor Cyan
Write-Host "Остановить: Ctrl+C" -ForegroundColor Cyan
Write-Host ""
& $ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -R "80:localhost:$Port" nokey@localhost.run
