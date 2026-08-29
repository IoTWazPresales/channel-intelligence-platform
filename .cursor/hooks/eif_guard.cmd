@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "SCRIPT=%~dp0eif_guard.py"

REM Cursor 3.12 Windows pipes hook JSON on stdin. PATH lookup must not consume
REM that pipe, and ERRORLEVEL must not be expanded inside a parenthesized block
REM (that captures the `where` result, not Python's exit code).
where python <nul >nul 2>&1
if not errorlevel 1 goto :run_python
where py <nul >nul 2>&1
if not errorlevel 1 goto :run_py
where python3 <nul >nul 2>&1
if not errorlevel 1 goto :run_python3
echo EIF hook launcher: no Python interpreter found on PATH (tried python, py -3, python3) 1>&2
exit /b 1

:run_python
python -u -X utf8 "%SCRIPT%"
exit /b !ERRORLEVEL!

:run_py
py -3 -u -X utf8 "%SCRIPT%"
exit /b !ERRORLEVEL!

:run_python3
python3 -u -X utf8 "%SCRIPT%"
exit /b !ERRORLEVEL!
