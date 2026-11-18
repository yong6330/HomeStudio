param(
    [string]$Password,
    [string]$CameraIp = "192.168.0.32"
)

if (-not $Password) {
    $Password = $env:HOMESTUDIO_CAM_PASSWORD
}

$ffmpeg = "C:\HomeStudio\tools\ffmpeg\bin\ffmpeg.exe"
$subUrl = "rtsp://codex:$Password@$CameraIp:554/media/video2"
$outMp4 = "C:\HomeStudio\test_clip_10s.mp4"
$outJpg = "C:\HomeStudio\snapshot_test.jpg"

Write-Host "Recording 10s MP4 clip from $CameraIp using -c:v copy..."
& $ffmpeg -y -nostdin -loglevel info -rtsp_transport tcp -i $subUrl -t 10 -c:v copy -tag:v hvc1 -an $outMp4

if (Test-Path $outMp4) {
    $size = (Get-Item $outMp4).Length
    Write-Host "SUCCESS: 5s MP4 clip recorded! Size: $size bytes"
    
    # Extract snapshot
    & $ffmpeg -y -nostdin -loglevel error -ss 0.5 -i $outMp4 -vframes 1 $outJpg
    if (Test-Path $outJpg) {
        $jpgSize = (Get-Item $outJpg).Length
        Write-Host "SUCCESS: Snapshot extracted from MP4! Size: $jpgSize bytes"
    }
} else {
    Write-Host "FAILED: MP4 clip not created"
}
