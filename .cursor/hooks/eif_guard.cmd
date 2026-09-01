@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "SCRIPT=%~dp0eif_guard.py"

REM Cursor 3.12 Windows pipes hook JSON on stdin. PATH lookup must not consume
REM that pipe, and ERRORLEVEL must not be expanded inside a parenthesized block
REM (that captures the `where` result, not Python's exit code).
REM A valid permission JSON object is always exit 0 so failClosed does not treat
REM an EIF deny/allow/crash-report as a mute "hook returned no output" failure.
where python <nul >nul 2>&1
if not errorlevel 1 goto :run_python
where py <nul >nul 2>&1
if not errorlevel 1 goto :run_py
where python3 <nul >nul 2>&1
if not errorlevel 1 goto :run_python3
call :emit_static failclosed HOOK_LAUNCHER_ERROR "no Python interpreter found on PATH (tried python, py -3, python3)"
exit /b 0

:run_python
python -u -X utf8 "%SCRIPT%"
if !ERRORLEVEL! == 0 exit /b !ERRORLEVEL!
goto :python_failed

:run_py
py -3 -u -X utf8 "%SCRIPT%"
if !ERRORLEVEL! == 0 exit /b !ERRORLEVEL!
goto :python_failed

:run_python3
python3 -u -X utf8 "%SCRIPT%"
if !ERRORLEVEL! == 0 exit /b !ERRORLEVEL!
goto :python_failed

:python_failed
call :emit_static crash HOOK_INTERNAL_ERROR "Python interpreter exited before a permission JSON decision"
exit /b 0

:emit_static
if defined CURSOR_PROJECT_DIR (
  set "EIF_ROOT=%CURSOR_PROJECT_DIR%"
) else (
  set "EIF_ROOT=%CD%"
)
if not exist "%EIF_ROOT%\.eif" mkdir "%EIF_ROOT%\.eif" >nul 2>&1
>>"%EIF_ROOT%\.eif\hook-guard.log" echo %~2: %~3
if exist "%~dp0eif_guard_%~1.json" (
  type "%~dp0eif_guard_%~1.json"
) else (
  echo {"permission":"deny","reason_code":"%~2","user_message":"%~2: %~3","agent_message":"%~2: %~3"}
)
goto :eof
