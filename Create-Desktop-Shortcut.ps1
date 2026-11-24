$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Skybox Recon.lnk'
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $root 'SkyboxRecon.exe'
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Skybox Recon desktop control centre'
$shortcut.Save()
Write-Host "Created: $shortcutPath"
