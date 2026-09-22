param(
    [string]$Python = "python",
    [string]$CairoDirectory = $env:IMAGE2SVG_CAIRO_DIR
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    & $Python -m pip install -e ".[qa,pptx,gui]"
    $Arguments = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name", "image2svg-gui",
        "--collect-all", "vtracer",
        "--add-data", "$ProjectRoot\src\image2svg\ai\scripts;image2svg\ai\scripts",
        "--hidden-import", "tkinter"
    )
    if ($CairoDirectory) {
        $ResolvedCairo = Resolve-Path -LiteralPath $CairoDirectory
        $CairoDlls = @(
            "libcairo-2.dll",
            "libfontconfig-1.dll",
            "libfreetype-6.dll",
            "libgcc_s_seh-1.dll",
            "libpixman-1-0.dll",
            "libpng16-16.dll",
            "libstdc++-6.dll",
            "libwinpthread-1.dll",
            "zlib1.dll",
            "libexpat-1.dll",
            "libbrotlidec.dll",
            "libbrotlicommon.dll",
            "libbz2-1.dll",
            "libharfbuzz-0.dll",
            "libgraphite2.dll",
            "libglib-2.0-0.dll",
            "libintl-8.dll",
            "libpcre2-8-0.dll",
            "libiconv-2.dll"
        )
        foreach ($Dll in $CairoDlls) {
            $DllPath = Join-Path $ResolvedCairo.Path $Dll
            if (-not (Test-Path -LiteralPath $DllPath)) {
                throw "Missing Cairo dependency: $DllPath"
            }
            $Arguments += @("--add-binary", "$DllPath;.")
        }
    }
    $PythonPrefix = (& $Python -c "import sys; print(sys.prefix)").Trim()
    foreach ($RuntimeDll in @("ffi-8.dll", "libexpat.dll")) {
        $RuntimeDllPath = Join-Path $PythonPrefix "Library\bin\$RuntimeDll"
        if (Test-Path -LiteralPath $RuntimeDllPath) {
            $Arguments += @("--add-binary", "$RuntimeDllPath;.")
        }
    }
    $Arguments += "src/image2svg/gui.py"
    & $Python @Arguments
} finally {
    Pop-Location
}
