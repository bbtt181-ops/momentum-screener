@echo off
echo Updating "MomentumScreenerDailyScan" to run daily at 22:00...
schtasks /change /tn "MomentumScreenerDailyScan" /st 22:00
echo.
echo Done. Verifying the new schedule:
schtasks /query /tn "MomentumScreenerDailyScan" /v /fo LIST | findstr /i "TaskName \"Start Time\" \"Next Run Time\""
echo.
pause
