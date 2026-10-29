@echo off
echo The daily scan now runs in the cloud (GitHub Actions, .github/workflows/daily_scan.yml).
echo Removing the old local Scheduled Tasks so they stop running on this PC...
schtasks /delete /f /tn "MomentumScreenerDailyScan"
schtasks /delete /f /tn "MomentumScreenerWatchdog"
echo.
echo Done. Verifying (both should say "cannot find"):
schtasks /query /tn "MomentumScreenerDailyScan"
schtasks /query /tn "MomentumScreenerWatchdog"
echo.
pause
