param([switch]$VerifyOnly,[switch]$Remove)
$ErrorActionPreference = 'Stop'
$labDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$expected = @(
  @{label='Python';path=(Join-Path $labDirectory 'runtime\host\asr-python.exe')}
)
$groupName = 'Capshumee Offline'
$records = @()
foreach ($program in $expected) {
  if ($Remove) {
    foreach ($direction in @('Outbound','Inbound')) {
      $name = "Capshumee-$($program.label)-$direction-Block"
      $existing = Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
      if ($existing -and ($existing | Get-NetFirewallApplicationFilter).Program -eq $program.path) { $existing | Remove-NetFirewallRule -ErrorAction Stop }
    }
    continue
  }
  if (-not (Test-Path -LiteralPath $program.path -PathType Leaf)) { throw "ASR executable missing: $($program.path)" }
  foreach ($direction in @('Outbound','Inbound')) {
    $ruleName = "Capshumee-$($program.label)-$direction-Block"
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if (-not $VerifyOnly) {
      if ($null -eq $rule) {
        New-NetFirewallRule -Name $ruleName -DisplayName "Capshumee $($program.label) $direction block" -Group $groupName -Description 'User-requested network block for dedicated local ASR only.' -Direction $direction -Action Block -Enabled True -Profile Any -Program $program.path -Protocol Any -ErrorAction Stop | Out-Null
      } else {
        Set-NetFirewallRule -Name $ruleName -Direction $direction -Action Block -Enabled True -Profile Any -Protocol Any -ErrorAction Stop | Out-Null
        $rule | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter -Program $program.path -ErrorAction Stop | Out-Null
      }
      $rule = Get-NetFirewallRule -Name $ruleName -PolicyStore ActiveStore -ErrorAction Stop
    }
    if ($VerifyOnly) { $rule = Get-NetFirewallRule -Name $ruleName -PolicyStore ActiveStore -ErrorAction Stop }
    if ($null -eq $rule) { throw "Required ASR firewall rule is missing: $ruleName" }
    $application = $rule | Get-NetFirewallApplicationFilter
    $portFilter = $rule | Get-NetFirewallPortFilter
    if ($rule.Enabled.ToString() -ne 'True' -or $rule.Action.ToString() -ne 'Block' -or $rule.Direction.ToString() -ne $direction -or $rule.Profile.ToString() -ne 'Any' -or $application.Program -ne $program.path -or $portFilter.Protocol.ToString() -ne 'Any') { throw "ASR firewall rule has changed: $ruleName" }
    $records += [PSCustomObject]@{name=$ruleName;program=$application.Program;direction=$direction;enabled=$true;action='Block';profiles='Any';protocol='Any'}
  }
}
if ($Remove) { Write-Output 'Capshumee firewall rules removed for this installation.'; exit 0 }
$profiles = @(Get-NetFirewallProfile | Select-Object Name,Enabled)
if (@($profiles | Where-Object { -not $_.Enabled }).Count -gt 0) { throw 'A Windows firewall profile is disabled; offline ASR is blocked from starting.' }
if ((Get-Service -Name mpssvc).Status -ne 'Running') { throw 'Windows Firewall service is not running.' }
$result = [PSCustomObject]@{verified=$true;verifiedAt=(Get-Date).ToString('o');scope='Only dedicated ASR executables';profiles=$profiles;rules=$records}
$result | ConvertTo-Json -Depth 5
