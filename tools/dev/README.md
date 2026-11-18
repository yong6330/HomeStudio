# Dev mock data

`seed_mock.py` builds a **separate** HomeStudio base dir filled with deterministic, synthetic hamster data. It refuses
the real install (`C:\HomeStudio`, `D:\HomeStudio`, the configured default, or any dir with `logs/service.log`) and only
wipes dirs it created itself (`.homestudio_mock` marker, `--force`).

```powershell
python tools\dev\seed_mock.py --out C:\HomeStudioDev --seed 7 --force
$env:HOMESTUDIO_BASE_DIR = "C:\HomeStudioDev"; python -m software.backend.api   # http://127.0.0.1:8080
```
macOS/Linux: `python tools/dev/seed_mock.py --out ./dev_data --force && HOMESTUDIO_BASE_DIR=./dev_data python -m software.backend.api`

What you get (defaults `--days 12 --seed 7`):
- 12:00-12:00 care days, nocturnal activity (mostly 20:00-04:00 KST), sessions of <=60 s events with tracks.
- Day -6: 3 h camera offline (excluded from the baseline, offline notification). Day -2: 40 min dark spell. Day -1: privacy on/off.
- Day -3: low activity -> end-of-day verdict notification when it closed. Today: low activity (home chip only, no mid-day alert).
- Long no-motion stretch ending now (> usual longest daily gap x1.5) -> "평소보다 오래 움직임이 보이지 않아요" (`--no-inactivity` to skip).
- Thumbnails/clips (synthetic "MOCK" frames, H.264 via ffmpeg) for the last `--clips-days` days.
- No accounts: the first visit runs signup + onboarding; the email code is printed in the API log (dev mail sender).
- `--now 2026-10-10T23:00:00+09:00` pins the clock for reproducible screenshots.

## Verification codes in development (audit item 8)

No mail sender is configured yet. Codes are **never** written to the server log. To receive them while developing,
start the API with `HOMESTUDIO_DEV_MAIL=1`; codes are appended to `<data dir>/dev_mail.log` (owner-only file).
`software/ui_build/shots.py --log <data dir>/dev_mail.log` reads codes from there. Default is off.

The first admin can only sign up from the HomeStudio PC itself (`http://127.0.0.1:8080`); everyone else joins with an invite code.
