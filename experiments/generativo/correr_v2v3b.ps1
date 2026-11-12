# Corrida real de V2 y V3b (piloto y estudio de 5 repeticiones) con DeepSeek y Kimi.
#
# Ejecutar desde una red que permita las API de DeepSeek (api.deepseek.com) y Kimi (api.moonshot.ai):
#   powershell -ExecutionPolicy Bypass -File experiments\generativo\correr_v2v3b.ps1
#   powershell -ExecutionPolicy Bypass -File experiments\generativo\correr_v2v3b.ps1 -SoloPiloto
#
# Las claves se escriben con entrada oculta, viven solo en este proceso y no se guardan en ningún archivo.
# La persona que autoriza el gasto firma con su nombre; el arnés se detiene antes de superar cada tope.
param([switch]$SoloPiloto)
$ErrorActionPreference = 'Stop'
$raiz = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $raiz
$py = Join-Path (Split-Path $raiz -Parent) 'mini-format-wt\venv-int\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$env:PYTHONIOENCODING = 'utf-8'
$cfgPiloto = 'experiments\generativo\configs\piloto_v2v3b.yaml'
$cfgEstudio = 'experiments\generativo\configs\estudio_v2v3b.yaml'
$tarifas = 'experiments\generativo\configs\tarifas_v2v3b_2026-11.json'

function Leer-Clave([string]$nombre) {
  $s = Read-Host "Pega la clave $nombre (no se muestra)" -AsSecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

function Probar-Api([string]$nombre, [string]$url, [string]$clave) {
  try {
    $r = Invoke-WebRequest -Uri $url -Headers @{ Authorization = "Bearer $clave" } -UseBasicParsing -TimeoutSec 30
    Write-Host ("  {0}: responde ({1})" -f $nombre, $r.StatusCode)
  } catch {
    $codigo = $null
    if ($_.Exception.Response) { $codigo = [int]$_.Exception.Response.StatusCode }
    throw ("{0} no responde desde esta red (HTTP {1}). No se hizo ninguna llamada de generación." -f $nombre, $codigo)
  }
}

try {
  Write-Host '1/5 Claves de API (no se muestran ni se guardan)'
  $env:DEEPSEEK_API_KEY = Leer-Clave 'DEEPSEEK_API_KEY'
  $env:MOONSHOT_API_KEY = Leer-Clave 'MOONSHOT_API_KEY'

  Write-Host '2/5 Conectividad (consulta de modelos, sin costo)'
  Probar-Api 'DeepSeek' 'https://api.deepseek.com/models' $env:DEEPSEEK_API_KEY
  Probar-Api 'Kimi' 'https://api.moonshot.ai/v1/models' $env:MOONSHOT_API_KEY

  Write-Host '3/5 Autorización del gasto'
  $firma = Read-Host 'Nombre completo de quien autoriza'
  $topePiloto = Read-Host 'Tope del piloto en USD (sugerido 5)'
  & $py experiments\generativo\autorizar_presupuesto.py $cfgPiloto $topePiloto $firma
  if (-not $SoloPiloto) {
    $topeEstudio = Read-Host 'Tope del estudio en USD (sugerido 20)'
    & $py experiments\generativo\autorizar_presupuesto.py $cfgEstudio $topeEstudio $firma
  }

  Write-Host '4/5 Piloto real (360 llamadas primarias)'
  & $py experiments\generativo\run.py ejecutar --config $cfgPiloto --adapter real --confirmar-real `
      --max-costo-usd $topePiloto --tarifas $tarifas --emitir-evidencia piloto-v2v3b
  if ($LASTEXITCODE -ne 0) { throw "el piloto terminó con código $LASTEXITCODE (ver resultados\real\piloto_v2v3b)" }

  if (-not $SoloPiloto) {
    Write-Host '5/5 Estudio de 5 repeticiones (1 400 llamadas primarias)'
    & $py experiments\generativo\run.py ejecutar --config $cfgEstudio --adapter real --confirmar-real `
        --max-costo-usd $topeEstudio --tarifas $tarifas --emitir-evidencia estudio-v2v3b
    if ($LASTEXITCODE -ne 0) { throw "el estudio terminó con código $LASTEXITCODE (ver resultados\real\estudio_v2v3b)" }
  }
  Write-Host 'Listo. Resultados en experiments\generativo\resultados\real\ y corridas en evidencia\corridas\.'
} finally {
  Remove-Item Env:\DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:\MOONSHOT_API_KEY -ErrorAction SilentlyContinue
}
