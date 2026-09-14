function Invoke-PythonCapture {
    param([string]$Executable, [string[]]$ToolArgs, [string]$WorkDir, [string]$Log)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $quoted = foreach ($arg in $ToolArgs) {
        $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
        $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
        '"' + $escaped + '"'
    }
    $info.Arguments = $quoted -join ' '
    $info.WorkingDirectory = $WorkDir
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $info.StandardOutputEncoding = $utf8
    $info.StandardErrorEncoding = $utf8
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $outText = $stdout.GetAwaiter().GetResult()
    $errText = $stderr.GetAwaiter().GetResult()
    [Console]::Out.Write($outText)
    [Console]::Error.Write($errText)
    [IO.File]::AppendAllText($Log, ($outText + $errText).Replace("`r`n", "`n"), $utf8)
    $code = $process.ExitCode
    $process.Dispose()
    return $code
}
