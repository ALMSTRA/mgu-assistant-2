<#
  Build de MGU Assistant 2 para Windows (onedir, dos ejecutables: GUI + consola).
  Uso (raiz de v2):  ./packaging/windows/build.ps1
  Resultado:         dist/MGU-Assistant-2/MGU-Assistant-2.exe  (+ mgua2-cli.exe)
#>
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
# Una instancia abierta desde dist/ bloquea las DLL de Qt y deja el build a medias.
$running = Get-Process -Name "MGU-Assistant-2","mgua2-cli" -ErrorAction SilentlyContinue
if ($running) { throw "Cierre MGU Assistant 2 antes de compilar (procesos: $($running.Id -join ', '))." }
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt
& $py -m PyInstaller --noconfirm --clean packaging\mgua2.spec
$exe = Join-Path $root "dist\MGU-Assistant-2\MGU-Assistant-2.exe"
if (-not (Test-Path $exe)) { throw "No se genero el ejecutable." }
Write-Host "LISTO: $exe"
Write-Host "Demo:  dist\MGU-Assistant-2\MGU-Assistant-2.exe --demo"
Write-Host "Firma (opcional): signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 `"$exe`""
