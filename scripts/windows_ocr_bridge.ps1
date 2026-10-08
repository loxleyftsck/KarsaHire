$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$LanguageTag = $env:KARSAHIRE_WINDOWS_OCR_LANGUAGE
if ($LanguageTag -notmatch '^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$') {
    [Console]::Error.WriteLine('Windows OCR language tag is invalid.')
    exit 2
}

function Wait-WinRtOperation([object]$Operation, [Type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
            $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.IsGenericType -and
            $_.GetParameters()[0].ParameterType.GetGenericTypeDefinition().FullName -eq
                'Windows.Foundation.IAsyncOperation`1'
        } |
        Select-Object -First 1
    if ($null -eq $method) {
        throw 'Windows OCR asynchronous adapter is unavailable.'
    }
    $closedMethod = $method.MakeGenericMethod($ResultType)
    $task = $closedMethod.Invoke($null, [object[]]@($Operation))
    $task.Wait()
    return $task.GetAwaiter().GetResult()
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $ocrType = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $languageType = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
    $availableTags = @($ocrType::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
    if ($availableTags -notcontains $LanguageTag) {
        throw 'Requested Windows OCR language is not installed.'
    }

    $language = $languageType::new($LanguageTag)
    $engine = $ocrType::TryCreateFromLanguage($language)
    if ($null -eq $engine) {
        throw 'Windows OCR engine could not be created for the requested language.'
    }

    $stdinStream = [Console]::OpenStandardInput()
    $buffer = [System.IO.MemoryStream]::new()
    $stdinStream.CopyTo($buffer)
    if ($buffer.Length -eq 0 -or $buffer.Length -gt 100MB) {
        throw 'Input image is empty or exceeds the local OCR bridge limit.'
    }

    $streamType = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime]
    $writerType = [Windows.Storage.Streams.DataWriter, Windows.Storage, ContentType = WindowsRuntime]
    $decoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $softwareBitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
    $ocrResultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
    $randomAccessStream = $streamType::new()
    $writer = $writerType::new($randomAccessStream.GetOutputStreamAt(0))
    $writer.WriteBytes($buffer.ToArray())
    [void](Wait-WinRtOperation -Operation ($writer.StoreAsync()) -ResultType ([uint32]))
    $writer.DetachStream() | Out-Null
    $randomAccessStream.Seek(0)

    $decoder = Wait-WinRtOperation -Operation ($decoderType::CreateAsync($randomAccessStream)) -ResultType $decoderType
    $bitmap = Wait-WinRtOperation -Operation ($decoder.GetSoftwareBitmapAsync()) -ResultType $softwareBitmapType
    $recognized = Wait-WinRtOperation -Operation ($engine.RecognizeAsync($bitmap)) -ResultType $ocrResultType
    foreach ($line in $recognized.Lines) {
        [Console]::Out.WriteLine($line.Text)
    }
}
catch {
    [Console]::Error.WriteLine(('Windows OCR bridge failed: ' + $_.Exception.Message))
    exit 2
}
