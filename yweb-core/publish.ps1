<#
.SYNOPSIS
    构建并发布 yweb 到 PyPI（或 testpypi）。

.DESCRIPTION
    执行完整的打包发布流程：清理旧产物 → python -m build → 验证产物 → twine upload。
    版本号从 pyproject.toml 自动读取，上传使用 .pypirc 里配置的 token。

.PARAMETER Repo
    上传目标仓库：pypi（默认）或 testpypi。

.PARAMETER SkipUpload
    只构建不上传，用于本地验证产物内容。

.EXAMPLE
    .\publish.ps1                         # 构建并发布到正式 PyPI
    .\publish.ps1 -Repo testpypi          # 构建并发布到 testpypi
    .\publish.ps1 -SkipUpload             # 只构建，产物留在 dist/
#>

[CmdletBinding()]
param(
    [ValidateSet("pypi", "testpypi")]
    [string]$Repo = "pypi",

    [switch]$SkipUpload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ---------- 0. 前置检查 ----------
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyproject = Join-Path $root "pyproject.toml"
$pypirc = Join-Path $root ".pypirc"

if (-not (Test-Path $pyproject)) {
    Write-Error "找不到 pyproject.toml，请在打包根目录下运行本脚本"
    exit 1
}

# 从 pyproject.toml 读版本号（简单正则，不依赖 Python toml 库）
$versionLine = Select-String -Path $pyproject -Pattern '^\s*version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) {
    Write-Error "无法从 pyproject.toml 解析 version 字段"
    exit 1
}
$version = $versionLine.Matches[0].Groups[1].Value
Write-Host "📦 版本号: $version" -ForegroundColor Cyan
Write-Host "🎯 目标仓库: $Repo" -ForegroundColor Cyan

if (-not $SkipUpload -and -not (Test-Path $pypirc)) {
    Write-Error "找不到 .pypirc 文件。请在 $root\.pypirc 中配置 $Repo 的 token。"
    exit 1
}

# ---------- 1. 清理旧产物 ----------
Write-Host "`n[1/4] 清理旧产物..." -ForegroundColor Yellow
foreach ($dir in @("dist", "build", "yweb.egg-info")) {
    $path = Join-Path $root $dir
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        Write-Host "  已删除 $dir/"
    }
}

# ---------- 2. 构建 ----------
Write-Host "`n[2/4] 构建 wheel + sdist..." -ForegroundColor Yellow
Push-Location $root
try {
    python -m build 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "构建失败，退出码: $LASTEXITCODE"
        exit 1
    }
} finally {
    Pop-Location
}

# ---------- 3. 验证产物 ----------
Write-Host "`n[3/4] 验证产物..." -ForegroundColor Yellow
$distDir = Join-Path $root "dist"
$wheel = Get-ChildItem $distDir -Filter "*.whl" -ErrorAction SilentlyContinue
$sdist = Get-ChildItem $distDir -Filter "*.tar.gz" -ErrorAction SilentlyContinue

if (-not $wheel -or -not $sdist) {
    Write-Error "构建产物不完整，dist/ 下应有 .whl 和 .tar.gz 各一个"
    exit 1
}

Write-Host "  ✅ $($wheel.Name)  ($([math]::Round($wheel.Length / 1KB, 1)) KB)"
Write-Host "  ✅ $($sdist.Name)  ($([math]::Round($sdist.Length / 1KB, 1)) KB)"

# 版本一致性检查
$expectedWheel = "yweb-$version-py3-none-any.whl"
if ($wheel.Name -ne $expectedWheel) {
    Write-Warning "wheel 文件名 ($($wheel.Name)) 与 pyproject.toml 版本 ($version) 不一致"
}

# ---------- 4. 上传 ----------
if ($SkipUpload) {
    Write-Host "`n⏭️  跳过上传（-SkipUpload）" -ForegroundColor DarkGray
    Write-Host "    产物在 $distDir"
    exit 0
}

Write-Host "`n[4/4] 上传到 $Repo..." -ForegroundColor Yellow
Push-Location $root
try {
    $repoArg = if ($Repo -eq "testpypi") { "--repository testpypi" } else { "" }
    python -m twine upload --config-file .pypirc $repoArg dist/* 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "上传失败，退出码: $LASTEXITCODE"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`n🎉 yweb $version 已发布到 $Repo！" -ForegroundColor Green
$publishUrl = if ($Repo -eq "testpypi") {
    "https://test.pypi.org/project/yweb/$version/"
} else {
    "https://pypi.org/project/yweb/$version/"
}
Write-Host "🔗 $publishUrl" -ForegroundColor Green
