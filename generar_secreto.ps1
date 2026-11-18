# Genera un secreto JWT aleatorio en el .env si la linea JWT_SECRET_KEY esta vacia.
# Lo llama iniciar_api.cmd; no requiere nada instalado (PowerShell viene con Windows).
param([string]$Ruta = (Join-Path $PSScriptRoot '.env'))
$archivo = $Ruta
if (-not (Test-Path $archivo)) { Write-Output 'no-hay-env'; exit 0 }
$s = Get-Content $archivo -Raw
if ($s -match 'JWT_SECRET_KEY=\s*(\r?\n|$)') {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $clave = [Convert]::ToBase64String($bytes)
    $s = $s -replace 'JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$clave"
    Set-Content -Path $archivo -Value $s -NoNewline
    Write-Output 'secreto-generado'
} else {
    Write-Output 'secreto-ya-existente'
}
