# 4 - Read-only check from the PC, and the D17 measurement.   Windows PowerShell 5.1, curl.exe
#
#   powershell -ExecutionPolicy Bypass -File .\krk_probe.ps1
#
# The password is asked for in a dialog (Get-Credential): it is never in the command line or
# the history, and goes to curl on stdin. The token stays in a variable and is shown only as
# its length and the first 6 characters.
#
# D17: if a GET with a valid token answers 401 where 200 is expected, the script prints the full
# response and headers and the UTC time, for the line in the cabinet's log. It does not retry.
param(
    [string]$Cabinet = "http://100.65.235.29",
    [string]$Email = "erp@lika.solutions",
    [int]$PedestalPk = 0
)
$ErrorActionPreference = "Stop"
$tmp = Join-Path $env:TEMP ("krk_probe_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $tmp | Out-Null
$results = @()

function Probe($name, $method, $path, $expect, $tok, $body = $null) {
    $b = Join-Path $tmp "body.txt"; $h = Join-Path $tmp "hdr.txt"
    $args_ = @("-s", "-m", "20", "-X", $method, "-o", $b, "-D", $h, "-w", "%{http_code}",
               "-H", "Authorization: Bearer $tok")
    $utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    if ($body) {
        $code = $body | & curl.exe @args_ -H "Content-Type: application/json" --data-binary "@-" "$Cabinet$path"
    } else {
        $code = & curl.exe @args_ "$Cabinet$path"
    }
    $text = if (Test-Path $b) { Get-Content $b -Raw } else { "" }
    if ($null -eq $text) { $text = "" }
    $ok = ("$code" -eq "$expect")
    $short = $text.Substring(0, [Math]::Min(160, $text.Length)) -replace "\s+", " "
    Write-Host ("{0,-4} {1,-26} {2,-6} {3} (ocekivano {4})  {5}" -f ($(if ($ok) {"OK"} else {"!!"})), $name, $method, $code, $expect, $short)
    if ("$code" -eq "401" -and "$expect" -eq "200") {
        Write-Host "     >>> D17 REPRODUCIRAN  $utc  $method $path"
        Write-Host "     --- zaglavlja ---"; Get-Content $h | ForEach-Object { Write-Host "     $_" }
        Write-Host "     --- tijelo ---"; Write-Host "     $text"
    }
    $script:results += [pscustomobject]@{ name = $name; code = "$code"; expect = "$expect"; ok = $ok; utc = $utc }
    return $text
}

try {
    $cred = Get-Credential -UserName $Email -Message "Lozinka servisnog racuna ERP-a na ormaru"
    $login = @{ email = $cred.UserName; password = $cred.GetNetworkCredential().Password } | ConvertTo-Json -Compress
    $out = $login | & curl.exe -s -m 20 -X POST -H "Content-Type: application/json" --data-binary "@-" -w "`n%{http_code}" "$Cabinet/api/auth/service-token"
    $login = $null; $cred = $null
    $arr = @($out); $code = "$($arr[-1])".Trim(); $json = ($arr[0..([Math]::Max(0, $arr.Count - 2))] -join "`n")
    if ($code -ne "200") { "service-token: $code  $json"; throw "nema tokena" }
    $t = $json | ConvertFrom-Json
    $tok = $t.access_token
    "service-token: 200  role=$($t.role) email=$($t.email)  token: $($tok.Length) znakova, pocinje '$($tok.Substring(0,6))'"
    if ($t.role -ne "api_client") { throw "uloga nije api_client" }
    ""

    Probe "pedestals.health"   GET  "/api/ext/pedestals/health" 200 $tok | Out-Null
    $peds = Probe "pedestals.list" GET "/api/ext/pedestals" 200 $tok
    if ($PedestalPk -eq 0) {
        try { $list = $peds | ConvertFrom-Json; $PedestalPk = [int]($list | Select-Object -First 1).id } catch { }
    }
    if ($PedestalPk -eq 0) { throw "ne znam pk ormara; pokreni s -PedestalPk N" }
    "     pk ormara za ostale pozive: $PedestalPk"
    Probe "berths.list"        GET  "/api/ext/berths" 200 $tok | Out-Null
    Probe "water.status_ext"   GET  "/api/ext/pedestals/$PedestalPk/water" 200 $tok | Out-Null
    Probe "pedestals.status_ext" GET "/api/ext/pedestals/$PedestalPk/status" 200 $tok | Out-Null
    # excluded, through the gateway -> 403 "Endpoint not allowed"
    Probe "camera.snapshot"    GET  "/api/ext/camera/$PedestalPk/snapshot" 403 $tok | Out-Null
    # excluded, a direct ext route -> 503 "Not enabled" (aa1f74f ext_pedestal_endpoints.py:394-397)
    Probe "camera.frame_ext"   GET  "/api/ext/pedestals/$PedestalPk/camera/frame" 503 $tok | Out-Null
    # a write -> 403 at the allow-list, before anything is forwarded (external_api_gateway.py:286-302).
    # Socket "Q9" does not exist: even if the gateway were wrong, there is nothing to switch.
    Probe "controls.socket_cmd" POST "/api/ext/controls/pedestal/$PedestalPk/socket/Q9/cmd" 403 $tok '{"action":"stop","reason":"ERP read-only probe"}' | Out-Null
    ""
    $bad = @($results | Where-Object { -not $_.ok })
    "SAZETAK: $($results.Count - $bad.Count)/$($results.Count) kako je ocekivano"
    $d17 = @($results | Where-Object { $_.code -eq "401" -and $_.expect -eq "200" })
    if ($d17.Count) { "D17: REPRODUCIRAN na $($d17.Count) poziva - vidi zaglavlja iznad; ne zaobilazi" }
    elseif (@($results | Where-Object { $_.expect -eq "200" -and $_.ok }).Count -ge 5) { "D17: NIJE reproduciran - svi GET-ovi s valjanim tokenom dali 200" }
    else { "D17: neodlucno - GET-ovi nisu dali 200, ali ni 401; vidi redove iznad" }
}
finally {
    $tok = $null
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
