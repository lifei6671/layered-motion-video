# Offline test speech only; this is not a TTS feature or a human approval.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$target = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $target) { throw 'Use a new output path' }
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SelectVoice('Microsoft Huihui Desktop')
    $synth.SetOutputToWaveFile($target)
    $synth.SpeakSsml('<speak version="1.0" xml:lang="zh-CN"><break time="700ms"/>预算是一百二十元，重量是两千克。<break time="1200ms"/>增长了百分之二十八，这是应用程序接口。<break time="1600ms"/>请再检查。<break time="600ms"/>请再检查。<break time="900ms"/></speak>')
} finally { $synth.Dispose() }
