@echo off
echo Creating "MomentumScreenerWatchdog" scheduled task (runs daily at 22:25,
echo 25 minutes after the main scan's 22:00 start time)...
schtasks /create /tn "MomentumScreenerWatchdog" /tr "\"C:\Users\PC\Desktop\momentum-screener\.venv\Scripts\python.exe\" \"C:\Users\PC\Desktop\momentum-screener\watchdog.py\"" /sc DAILY /st 22:25
echo.
echo Done. Verifying the new task:
schtasks /query /tn "MomentumScreenerWatchdog" /v /fo LIST | findstr /i "TaskName \"Start Time\" \"Next Run Time\""
echo.
echo NOTE: if you ever change the main scan's time away from 22:00, update this
echo task's time too (main time + ~25 minutes), e.g.:
echo   schtasks /change /tn "MomentumScreenerWatchdog" /st HH:MM
echo.
pause
