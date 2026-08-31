# Crea un acceso directo en el Escritorio para "Seguimiento y Planificacion",
# apuntando a iniciar.bat y usando icon.ico como icono.
# Este script se debe ejecutar desde dentro de la carpeta del proyecto
# (junto a iniciar.bat e icon.ico).

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetBat = Join-Path $scriptDir "iniciar.bat"
$iconFile = Join-Path $scriptDir "icon.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Seguimiento y Planificacion.lnk"

if (-not (Test-Path $targetBat)) {
    Write-Host ""
    Write-Host "ERROR: no se encontro iniciar.bat en esta carpeta." -ForegroundColor Red
    Write-Host "Asegurate de que este script este junto a iniciar.bat e icon.ico." -ForegroundColor Red
    Write-Host ""
    Read-Host "Presiona Enter para cerrar"
    exit 1
}

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $targetBat
$Shortcut.WorkingDirectory = $scriptDir
if (Test-Path $iconFile) {
    $Shortcut.IconLocation = $iconFile
}
$Shortcut.Description = "Seguimiento y Planificacion"
$Shortcut.WindowStyle = 1
$Shortcut.Save()

Write-Host ""
Write-Host "Listo! Se creo el acceso directo 'Seguimiento y Planificacion' en tu Escritorio." -ForegroundColor Green
Write-Host ""
Read-Host "Presiona Enter para cerrar"
