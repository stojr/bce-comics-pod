@echo off
REM ============================================================
REM  Download issue covers for every series (owned + small gaps).
REM  Just double-click this file. Safe to re-run — it skips covers
REM  already downloaded, so run it again if Comic Vine was busy.
REM ============================================================
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py"

echo Amazing Spider-Man...
%PY% scripts\fetch_issue_covers.py --series "Amazing Spider-Man" --id asm --data data\books.json
echo.
echo West Coast Avengers...
%PY% scripts\fetch_issue_covers.py --series "West Coast Avengers" --id wca --data data\wca.json --alt-series "Avengers West Coast"
echo.
echo Done. If lots said "no cover found", Comic Vine was rate-limited -
echo wait an hour and double-click this again (it resumes where it left off).
pause
