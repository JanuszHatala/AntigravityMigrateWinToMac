#Requires -Version 5.1
<#
.SYNOPSIS
    Zip Antigravity IDE, Antigravity 2.0, shared Gemini, and CLI trees for the Mac import script.

.DESCRIPTION
    Reads profile data from APPDATA and USERPROFILE (or -WindowsHome). Does not look
    beside this script for user data. Copies file bytes. Does not rewrite paths.

    Zip layout (stable):
      manifest.json
      profiles/ide/application-support/User/
      profiles/ide/application-support/argv.json
      profiles/ide/dot-antigravity-ide/
      profiles/ide/gemini-antigravity-ide/
      profiles/app/application-support/User/
      profiles/app/application-support/argv.json
      profiles/app/dot-antigravity/
      profiles/app/gemini-antigravity/
      profiles/app/application-support-antigravity/   (only when this folder is a different directory from Antigravity)
      profiles/gemini/GEMINI.md
      profiles/gemini/config/
      profiles/cli/antigravity-cli/
      also/<n>/                                        (no Mac path)

.PARAMETER Profile
    ide, app, gemini, or cli. Repeat the parameter, or pass a list. Default: every
    one of those trees that exists. cli is included only when its folder exists.

.PARAMETER OutputZip
    Absolute path of the zip to write. Required. Refused when the path is relative.

.PARAMETER Also
    Extra absolute folders (repositories). Not searched for automatically.

.PARAMETER WindowsHome
    Profile root when it is not USERPROFILE. Dot folders are read from this root.
    Roaming is then WindowsHome\AppData\Roaming, not the current APPDATA.

.PARAMETER DryRun
    Print the manifest lines and skipped cache paths. Do not write the zip.
#>
[CmdletBinding()]
param(
    [ValidateSet('ide', 'app', 'gemini', 'cli')]
    [string[]] $Profile,

    [string] $OutputZip,

    [string[]] $Also,

    [string] $WindowsHome,

    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
try {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
} catch {
}

$script:SkipDirectoryNames = @(
    'Cache'
    'CachedData'
    'Code Cache'
    'GPUCache'
    'logs'
    'Crashpad'
    'Service Worker'
    'blob_storage'
    'CachedExtensionVSIXs'
    'Session Storage'
    'Cookies'
)

$script:SkipFileNames = @(
    'Cookies'
    'Cookies-journal'
)

function Test-IsWindowsHost {
    $variable = Get-Variable -Name IsWindows -ErrorAction SilentlyContinue
    if ($null -ne $variable) {
        return [bool]$variable.Value
    }
    return $true
}

function Fail {
    param([string] $Message)
    [Console]::Error.WriteLine($Message)
    exit 1
}

function Test-AbsolutePath {
    param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }
    if (Test-IsWindowsHost) {
        if ($Path -match '^[A-Za-z]:\\') { return $true }
        if ($Path -match '^\\\\[^\\]+\\[^\\]+') { return $true }
        return $false
    }
    return $Path.StartsWith('/') -and -not $Path.StartsWith('//')
}

function Join-Segments {
    param(
        [string] $Base,
        [string[]] $Parts
    )
    $path = $Base
    foreach ($part in $Parts) {
        $path = Join-Path -Path $path -ChildPath $part
    }
    return $path
}

function Test-SameDirectory {
    param(
        [string] $Left,
        [string] $Right
    )
    if (-not (Test-Path -LiteralPath $Left -PathType Container)) { return $false }
    if (-not (Test-Path -LiteralPath $Right -PathType Container)) { return $false }
    $comparison = [System.StringComparison]::Ordinal
    if (Test-IsWindowsHost) {
        $comparison = [System.StringComparison]::OrdinalIgnoreCase
    }
    $l = [System.IO.Path]::GetFullPath($Left).TrimEnd('\', '/')
    $r = [System.IO.Path]::GetFullPath($Right).TrimEnd('\', '/')
    return $l.Equals($r, $comparison)
}

function Test-PathUnder {
    param(
        [string] $Child,
        [string] $Parent
    )
    if ([string]::IsNullOrWhiteSpace($Child) -or [string]::IsNullOrWhiteSpace($Parent)) {
        return $false
    }
    $comparison = [System.StringComparison]::Ordinal
    if (Test-IsWindowsHost) {
        $comparison = [System.StringComparison]::OrdinalIgnoreCase
    }
    $childFull = [System.IO.Path]::GetFullPath($Child).TrimEnd('\', '/')
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    if ($childFull.Equals($parentFull, $comparison)) { return $true }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    return $childFull.StartsWith($parentFull + $separator, $comparison)
}

function Test-NameInList {
    param(
        [string] $Name,
        [string[]] $Names
    )
    foreach ($candidate in $Names) {
        if ($Name.Equals($candidate, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function ConvertTo-JsonString {
    param([string] $Value)
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $chars = $Value.ToCharArray()
    for ($i = 0; $i -lt $chars.Length; $i++) {
        $code = [int]$chars[$i]
        if ($code -eq 34) {
            [void]$builder.Append('\"')
        } elseif ($code -eq 92) {
            [void]$builder.Append('\\')
        } elseif ($code -eq 10) {
            [void]$builder.Append('\n')
        } elseif ($code -eq 13) {
            [void]$builder.Append('\r')
        } elseif ($code -eq 9) {
            [void]$builder.Append('\t')
        } elseif ($code -lt 32) {
            [void]$builder.Append(('\u{0:x4}' -f $code))
        } else {
            [void]$builder.Append($chars[$i])
        }
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Get-CopyItems {
    param(
        [string] $Root,
        [bool] $ApplySkips,
        [bool] $KeepGeminiLogs,
        [string] $LocalAppData
    )
    $files = New-Object System.Collections.Generic.List[string]
    $dirs = New-Object System.Collections.Generic.List[string]
    $skipped = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        try {
            $children = [System.IO.Directory]::GetFileSystemEntries($current)
        } catch {
            Fail ("Cannot read " + $current + ": " + $_.Exception.Message)
        }
        foreach ($entry in $children) {
            $name = [System.IO.Path]::GetFileName($entry)
            $attributes = [System.IO.File]::GetAttributes($entry)
            $reparse = [System.IO.FileAttributes]::ReparsePoint
            if (($attributes -band $reparse) -ne 0) {
                [void]$skipped.Add($entry)
                continue
            }
            if ($LocalAppData -and (Test-PathUnder -Child $entry -Parent $LocalAppData)) {
                [void]$skipped.Add($entry)
                continue
            }
            $isDirectory = ($attributes -band [System.IO.FileAttributes]::Directory) -ne 0
            if ($isDirectory) {
                $skipDirectory = $ApplySkips -and (Test-NameInList -Name $name -Names $script:SkipDirectoryNames)
                if ($skipDirectory -and $KeepGeminiLogs -and $name.Equals('logs', [System.StringComparison]::OrdinalIgnoreCase)) {
                    $skipDirectory = $false
                }
                if ($skipDirectory) {
                    [void]$skipped.Add($entry)
                    continue
                }
                [void]$dirs.Add($entry)
                $stack.Push($entry)
            } else {
                if ($ApplySkips -and (Test-NameInList -Name $name -Names $script:SkipFileNames)) {
                    [void]$skipped.Add($entry)
                    continue
                }
                [void]$files.Add($entry)
            }
        }
    }
    return [pscustomobject]@{
        Files   = $files
        Dirs    = $dirs
        Skipped = $skipped
    }
}

function Get-RelativeUnix {
    param(
        [string] $Root,
        [string] $Full
    )
    $comparison = [System.StringComparison]::Ordinal
    if (Test-IsWindowsHost) {
        $comparison = [System.StringComparison]::OrdinalIgnoreCase
    }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $fullPath = [System.IO.Path]::GetFullPath($Full)
    $prefix = $rootFull + $separator
    if (-not $fullPath.StartsWith($prefix, $comparison)) {
        Fail "Path is outside its tree: $Full"
    }
    $relative = $fullPath.Substring($prefix.Length)
    return ($relative -replace '\\', '/')
}

function Add-ZipBytes {
    param(
        $Archive,
        [string] $EntryName,
        [byte[]] $Bytes
    )
    $entry = $Archive.CreateEntry($EntryName.Replace('\', '/'), [System.IO.Compression.CompressionLevel]::NoCompression)
    $stream = $entry.Open()
    try {
        $stream.Write($Bytes, 0, $Bytes.Length)
    } finally {
        $stream.Dispose()
    }
}

function Add-ZipFile {
    param(
        $Archive,
        [string] $EntryName,
        [string] $FilePath
    )
    $entry = $Archive.CreateEntry($EntryName.Replace('\', '/'), [System.IO.Compression.CompressionLevel]::Optimal)
    $inputStream = [System.IO.File]::Open(
        $FilePath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    $outputStream = $entry.Open()
    try {
        $inputStream.CopyTo($outputStream)
    } finally {
        $outputStream.Dispose()
        $inputStream.Dispose()
    }
}

if ([string]::IsNullOrWhiteSpace($OutputZip)) {
    Fail "-OutputZip is required and must be an absolute path."
}
$OutputZip = $OutputZip.Trim()
if (-not (Test-AbsolutePath $OutputZip)) {
    Fail "-OutputZip must be an absolute path. Refusing a relative path: $OutputZip"
}

$profileRoot = $env:USERPROFILE
$roaming = $env:APPDATA
$localAppData = $env:LOCALAPPDATA
if (-not [string]::IsNullOrWhiteSpace($WindowsHome)) {
    $profileRoot = $WindowsHome.Trim()
    $roaming = Join-Segments -Base $profileRoot -Parts @('AppData', 'Roaming')
    $localAppData = Join-Segments -Base $profileRoot -Parts @('AppData', 'Local')
}
if (-not (Test-AbsolutePath $profileRoot)) {
    Fail "The profile root is not an absolute path. Set USERPROFILE or pass -WindowsHome."
}
if (-not (Test-AbsolutePath $roaming)) {
    Fail "APPDATA is not an absolute path."
}

$explicitProfiles = $false
$requested = New-Object System.Collections.Generic.List[string]
if ($Profile -and $Profile.Count -gt 0) {
    $explicitProfiles = $true
    foreach ($name in $Profile) {
        if (-not $requested.Contains($name)) {
            [void]$requested.Add($name)
        }
    }
} else {
    foreach ($name in @('ide', 'app', 'gemini', 'cli')) {
        [void]$requested.Add($name)
    }
}

$trees = New-Object System.Collections.Generic.List[object]
function Add-Tree {
    param(
        [string] $TreeProfile,
        [string] $Id,
        [string] $Kind,
        [string] $Source,
        [string] $ZipPath,
        [string] $MacRelative,
        [bool] $KeepGeminiLogs
    )
    [void]$script:trees.Add([pscustomobject]@{
            Profile         = $TreeProfile
            Id              = $Id
            Kind            = $Kind
            Source          = $Source
            ZipPath         = $ZipPath
            MacRelative     = $MacRelative
            KeepGeminiLogs  = $KeepGeminiLogs
            ApplySkips      = $true
        })
}

Add-Tree 'ide' 'ide-user' 'dir' (Join-Segments $roaming @('Antigravity IDE', 'User')) 'profiles/ide/application-support/User' 'Library/Application Support/Antigravity IDE/User' $false
Add-Tree 'ide' 'ide-argv' 'file' (Join-Segments $roaming @('Antigravity IDE', 'argv.json')) 'profiles/ide/application-support/argv.json' 'Library/Application Support/Antigravity IDE/argv.json' $false
Add-Tree 'ide' 'ide-extensions' 'dir' (Join-Segments $profileRoot @('.antigravity-ide')) 'profiles/ide/dot-antigravity-ide' '.antigravity-ide' $false
Add-Tree 'ide' 'ide-gemini' 'dir' (Join-Segments $profileRoot @('.gemini', 'antigravity-ide')) 'profiles/ide/gemini-antigravity-ide' '.gemini/antigravity-ide' $true
Add-Tree 'app' 'app-user' 'dir' (Join-Segments $roaming @('Antigravity', 'User')) 'profiles/app/application-support/User' 'Library/Application Support/Antigravity/User' $false
Add-Tree 'app' 'app-argv' 'file' (Join-Segments $roaming @('Antigravity', 'argv.json')) 'profiles/app/application-support/argv.json' 'Library/Application Support/Antigravity/argv.json' $false
Add-Tree 'app' 'app-extensions' 'dir' (Join-Segments $profileRoot @('.antigravity')) 'profiles/app/dot-antigravity' '.antigravity' $false
Add-Tree 'app' 'app-gemini' 'dir' (Join-Segments $profileRoot @('.gemini', 'antigravity')) 'profiles/app/gemini-antigravity' '.gemini/antigravity' $true
Add-Tree 'gemini' 'gemini-rules' 'file' (Join-Segments $profileRoot @('.gemini', 'GEMINI.md')) 'profiles/gemini/GEMINI.md' '.gemini/GEMINI.md' $false
Add-Tree 'gemini' 'gemini-config' 'dir' (Join-Segments $profileRoot @('.gemini', 'config')) 'profiles/gemini/config' '.gemini/config' $true
Add-Tree 'cli' 'cli' 'dir' (Join-Segments $profileRoot @('.gemini', 'antigravity-cli')) 'profiles/cli/antigravity-cli' '.gemini/antigravity-cli' $true

$canonicalApp = Join-Segments $roaming @('Antigravity')
$lowerApp = Join-Segments $roaming @('antigravity')
if ((Test-Path -LiteralPath $lowerApp -PathType Container) -and -not (Test-SameDirectory $lowerApp $canonicalApp)) {
    Add-Tree 'app' 'app-lower' 'dir' $lowerApp 'profiles/app/application-support-antigravity' 'Library/Application Support/antigravity' $false
}

$entries = New-Object System.Collections.Generic.List[object]
$planned = New-Object System.Collections.Generic.List[object]
$skippedPaths = New-Object System.Collections.Generic.List[string]

foreach ($name in $requested) {
    $found = 0
    foreach ($tree in $trees) {
        if ($tree.Profile -ne $name) { continue }
        $exists = $false
        if ($tree.Kind -eq 'dir') {
            if (Test-Path -LiteralPath $tree.Source -PathType Leaf) {
                Fail "Expected a directory and found a file: $($tree.Source)"
            }
            $exists = Test-Path -LiteralPath $tree.Source -PathType Container
        } else {
            if (Test-Path -LiteralPath $tree.Source -PathType Container) {
                Fail "Expected a file and found a directory: $($tree.Source)"
            }
            $exists = Test-Path -LiteralPath $tree.Source -PathType Leaf
        }
        if (-not $exists) { continue }
        if ($localAppData -and (Test-PathUnder -Child $tree.Source -Parent $localAppData)) {
            Fail "Refusing a LocalAppData path: $($tree.Source)"
        }
        $found++
        $item = [pscustomobject]@{
            Profile        = $tree.Profile
            Id             = $tree.Id
            Kind           = $tree.Kind
            Source         = [System.IO.Path]::GetFullPath($tree.Source)
            ZipPath        = $tree.ZipPath
            MacRelative    = $tree.MacRelative
            KeepGeminiLogs = $tree.KeepGeminiLogs
            ApplySkips     = $true
        }
        [void]$entries.Add($item)
        [void]$planned.Add($item)
    }
    if ($explicitProfiles -and $found -eq 0) {
        Fail "Profile $name has no files to copy."
    }
}

$alsoIndex = 0
$seenAlso = New-Object 'System.Collections.Generic.HashSet[string]'
if ($Also) {
    foreach ($extra in $Also) {
        if ([string]::IsNullOrWhiteSpace($extra)) {
            Fail "-Also path is empty."
        }
        $extra = $extra.Trim()
        if (-not (Test-AbsolutePath $extra)) {
            Fail "-Also must be an absolute folder. Refusing: $extra"
        }
        if (-not (Test-Path -LiteralPath $extra -PathType Container)) {
            Fail "-Also folder does not exist: $extra"
        }
        if ($localAppData -and (Test-PathUnder -Child $extra -Parent $localAppData)) {
            Fail "Refusing a LocalAppData folder: $extra"
        }
        $fullExtra = [System.IO.Path]::GetFullPath($extra)
        if (-not $seenAlso.Add($fullExtra)) {
            Fail "-Also folder is listed twice: $fullExtra"
        }
        $alsoIndex++
        $item = [pscustomobject]@{
            Profile        = 'also'
            Id             = "also-$alsoIndex"
            Kind           = 'dir'
            Source         = $fullExtra
            ZipPath        = "also/$alsoIndex"
            MacRelative    = $null
            KeepGeminiLogs = $false
            ApplySkips     = $false
        }
        [void]$entries.Add($item)
        [void]$planned.Add($item)
    }
}

if ($entries.Count -eq 0) {
    Fail "Nothing to copy. No Antigravity trees were found."
}

$zipParent = Split-Path -Parent $OutputZip
if ([string]::IsNullOrWhiteSpace($zipParent) -or -not (Test-Path -LiteralPath $zipParent -PathType Container)) {
    Fail "Output directory does not exist: $zipParent"
}
if ((-not $DryRun) -and (Test-Path -LiteralPath $OutputZip)) {
    Fail "Output zip already exists: $OutputZip"
}

$filesById = New-Object 'System.Collections.Generic.Dictionary[string,object]'
$dirsById = New-Object 'System.Collections.Generic.Dictionary[string,object]'
$fileCount = 0
foreach ($item in $planned) {
    if ($item.Kind -eq 'file') {
        $fileCount++
        continue
    }
    $copied = Get-CopyItems -Root $item.Source -ApplySkips $item.ApplySkips -KeepGeminiLogs ([bool]$item.KeepGeminiLogs) -LocalAppData $localAppData
    $fileCount += $copied.Files.Count
    foreach ($skipped in $copied.Skipped) {
        [void]$skippedPaths.Add([string]$skipped)
    }
    $filesById[$item.Id] = $copied.Files
    $dirsById[$item.Id] = $copied.Dirs
}

if ($DryRun) {
    Write-Output "mode`tdry-run"
    Write-Output "Dry run. No zip written."
} else {
    Write-Output "mode`twrite"
}

Write-Output ("zip`t" + $OutputZip)
Write-Output ("windowsHome`t" + [System.IO.Path]::GetFullPath($profileRoot))
Write-Output ("roaming`t" + [System.IO.Path]::GetFullPath($roaming))
foreach ($item in $entries) {
    $mac = $item.MacRelative
    if ([string]::IsNullOrEmpty($mac)) { $mac = '-' }
    Write-Output ("entry`t{0}`t{1}`t{2}`t{3}`t{4}`t{5}" -f $item.Profile, $item.Id, $item.Kind, $item.Source, $item.ZipPath, $mac)
}
$sortedSkips = New-Object System.Collections.Generic.List[string]
foreach ($skipped in $skippedPaths) {
    [void]$sortedSkips.Add([string]$skipped)
}
$sortedSkips.Sort([StringComparer]::Ordinal)
for ($skipIndex = 0; $skipIndex -lt $sortedSkips.Count; $skipIndex++) {
    Write-Output ("skip`t" + $sortedSkips[$skipIndex])
}
Write-Output ("files`t" + $fileCount)

if ($DryRun) {
    exit 0
}

$manifestBuilder = New-Object System.Text.StringBuilder
[void]$manifestBuilder.Append('{"version":1,"windowsHome":')
[void]$manifestBuilder.Append((ConvertTo-JsonString ([System.IO.Path]::GetFullPath($profileRoot))))
[void]$manifestBuilder.Append(',"entries":[')
for ($index = 0; $index -lt $entries.Count; $index++) {
    if ($index -gt 0) { [void]$manifestBuilder.Append(',') }
    $item = $entries[$index]
    [void]$manifestBuilder.Append('{"profile":')
    [void]$manifestBuilder.Append((ConvertTo-JsonString $item.Profile))
    [void]$manifestBuilder.Append(',"id":')
    [void]$manifestBuilder.Append((ConvertTo-JsonString $item.Id))
    [void]$manifestBuilder.Append(',"kind":')
    [void]$manifestBuilder.Append((ConvertTo-JsonString $item.Kind))
    [void]$manifestBuilder.Append(',"source":')
    [void]$manifestBuilder.Append((ConvertTo-JsonString $item.Source))
    [void]$manifestBuilder.Append(',"zipPath":')
    [void]$manifestBuilder.Append((ConvertTo-JsonString $item.ZipPath))
    [void]$manifestBuilder.Append(',"macRelative":')
    if ([string]::IsNullOrEmpty($item.MacRelative)) {
        [void]$manifestBuilder.Append('null')
    } else {
        [void]$manifestBuilder.Append((ConvertTo-JsonString $item.MacRelative))
    }
    [void]$manifestBuilder.Append('}')
}
[void]$manifestBuilder.Append(']}')
$manifestJson = $manifestBuilder.ToString()
$manifestBytes = $utf8.GetBytes($manifestJson)

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = $null
$failed = $false
$failureMessage = ''
try {
    $archive = [System.IO.Compression.ZipFile]::Open($OutputZip, [System.IO.Compression.ZipArchiveMode]::Create)
    Add-ZipBytes -Archive $archive -EntryName 'manifest.json' -Bytes $manifestBytes
    foreach ($item in $planned) {
        if ($item.Kind -eq 'file') {
            Add-ZipFile -Archive $archive -EntryName $item.ZipPath -FilePath $item.Source
            continue
        }
        $directoryEntry = $item.ZipPath.TrimEnd('/') + '/'
        [void]$archive.CreateEntry($directoryEntry)
        $dirNames = New-Object System.Collections.Generic.List[string]
        $itemDirs = $dirsById[$item.Id]
        for ($dirIndex = 0; $dirIndex -lt $itemDirs.Count; $dirIndex++) {
            $relative = Get-RelativeUnix -Root $item.Source -Full $itemDirs[$dirIndex]
            [void]$dirNames.Add($item.ZipPath.TrimEnd('/') + '/' + $relative + '/')
        }
        $dirNames.Sort([StringComparer]::Ordinal)
        for ($dirIndex = 0; $dirIndex -lt $dirNames.Count; $dirIndex++) {
            [void]$archive.CreateEntry($dirNames[$dirIndex])
        }
        $entryNames = New-Object System.Collections.Generic.List[string]
        $entryToPath = New-Object 'System.Collections.Generic.Dictionary[string,string]'
        $itemFiles = $filesById[$item.Id]
        for ($fileIndex = 0; $fileIndex -lt $itemFiles.Count; $fileIndex++) {
            $filePath = [string]$itemFiles[$fileIndex]
            $relative = Get-RelativeUnix -Root $item.Source -Full $filePath
            $entryName = $item.ZipPath.TrimEnd('/') + '/' + $relative
            [void]$entryNames.Add($entryName)
            $entryToPath[$entryName] = $filePath
        }
        $entryNames.Sort([StringComparer]::Ordinal)
        for ($fileIndex = 0; $fileIndex -lt $entryNames.Count; $fileIndex++) {
            $entryName = [string]$entryNames[$fileIndex]
            Add-ZipFile -Archive $archive -EntryName $entryName -FilePath $entryToPath[$entryName]
        }
    }
} catch {
    $failed = $true
    $failureMessage = $_.Exception.Message
} finally {
    if ($archive) {
        $archive.Dispose()
        $archive = $null
    }
}

if ($failed) {
    if (Test-Path -LiteralPath $OutputZip) {
        Remove-Item -LiteralPath $OutputZip -Force
    }
    Fail $failureMessage
}

Write-Output ("wrote`t" + $OutputZip)
exit 0
