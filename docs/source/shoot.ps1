# Screenshot a local page with Microsoft Edge (headless) into a PNG.
#   powershell -File docs/source/shoot.ps1 <page.html|image.svg> <out.png> <width> <height> [scale] [query]
# An .svg is wrapped in a page first. The background stays transparent.
param($page, $png, [int]$w, [int]$h, [double]$scale = 1, $query = "")
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$src = (Resolve-Path $page).Path
if ($src.EndsWith('.svg')) {
    $html = [System.IO.Path]::ChangeExtension([System.IO.Path]::GetTempFileName(), '.html')
    $uri = ([System.Uri]$src).AbsoluteUri
    "<html><body style='margin:0;background:transparent'><img src='$uri' style='display:block;width:${w}px'></body></html>" |
        Set-Content -Encoding utf8 $html
    $src = $html
}
$url = ([System.Uri]$src).AbsoluteUri + $query
$out = [System.IO.Path]::GetFullPath($png)
& $edge --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 `
    --allow-file-access-from-files "--force-device-scale-factor=$scale" "--window-size=$w,$h" `
    "--screenshot=$out" $url 2>$null | Out-Null
Start-Sleep -Milliseconds 300
if (Test-Path $out) { "wrote $out" } else { "failed: $out" }
