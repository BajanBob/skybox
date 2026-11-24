$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Skybox Recon.lnk'
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $root 'Run-Skybox-Recon.bat'
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Skybox Recon command-line toolkit'
$shortcut.Save()
Write-Host "Created: $shortcutPath"
