# Overnight Crewline benchmarks. Run in PowerShell before sleeping:
#   powershell -ExecutionPolicy Bypass -File scripts\overnight.ps1   (from the repo root)
# Light load: agy only (2 calls at a time), no Docker. Every step resumes where it stopped.
# Logs: $env:CREWLINE_DATA\overnight-<date>.log

$ErrorActionPreference = "Continue"
$data = if ($env:CREWLINE_DATA) { $env:CREWLINE_DATA } else { "$HOME\.crewline" }
$log = "$data\overnight-$(Get-Date -Format yyyyMMdd-HHmm).log"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Keep the machine awake while this window runs (released when the script ends).
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

function Step($name, $argv) {
    "=== $(Get-Date -Format s) $name" | Tee-Object -FilePath $log -Append
    & uv run crewline @argv 2>&1 | Tee-Object -FilePath $log -Append
}

Step "Kafka: agent + locate hints (60)" @("eval", "hints", "--project", "kafka", "--n", "60")
Step "Flink: agent alone vs locate (40)" @("eval", "versus", "--project", "flink", "--n", "40")
Step "Flink: agent + locate hints (40)" @("eval", "hints", "--project", "flink", "--n", "40")

[Win32.Power]::SetThreadExecutionState([uint32]"0x80000000") | Out-Null   # ES_CONTINUOUS: back to normal
"=== $(Get-Date -Format s) done" | Tee-Object -FilePath $log -Append
