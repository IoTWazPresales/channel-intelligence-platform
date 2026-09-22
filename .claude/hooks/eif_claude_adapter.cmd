@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM Thin launcher: find an interpreter, run the adapter, pass its exit code
REM through unchanged. The adapter itself (eif_claude_adapter.py) owns the
REM single-decision emit guarantee and the fail-closed contract; this script
REM only adds the one guarantee it cannot: if the interpreter is missing, or
REM if the adapter exits with anything other than 0 or 2 (crash, OOM-kill,
REM interpreter killed before a decision), Claude Code must still see a
REM blocking exit code. Per Claude Code's documented hook contract, exit
REM code 2 alone blocks regardless of stdout, so no JSON body is required
REM on this path (unlike the Cursor launcher, which mirrors Cursor's
REM different exit-0-plus-JSON contract).
set "SCRIPT=%~dp0eif_claude_adapter.py"

"%SystemRoot%\System32\where.exe" python <nul >nul 2>&1
if not errorlevel 1 goto :select_python
"%SystemRoot%\System32\where.exe" py <nul >nul 2>&1
if not errorlevel 1 goto :select_py
"%SystemRoot%\System32\where.exe" python3 <nul >nul 2>&1
if not errorlevel 1 goto :select_python3
if exist "%SystemRoot%\py.exe" goto :select_py_root
>&2 echo EIF claude-code adapter fault SHIM_NO_INTERPRETER: no Python interpreter found on PATH (tried python, py -3, python3)
exit /b 2

:select_python
set "EIF_PYTHON=python"
set "EIF_PYTHON_ARGS="
goto :run
:select_py
set "EIF_PYTHON=py"
set "EIF_PYTHON_ARGS=-3"
goto :run
:select_python3
set "EIF_PYTHON=python3"
set "EIF_PYTHON_ARGS="
goto :run
:select_py_root
set "EIF_PYTHON=%SystemRoot%\py.exe"
set "EIF_PYTHON_ARGS=-3"

:run
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 "%SCRIPT%"
set "EIF_RC=%ERRORLEVEL%"
if "%EIF_RC%"=="0" exit /b 0
if "%EIF_RC%"=="2" exit /b 2
>&2 echo EIF claude-code adapter fault SHIM_LAUNCHER_CRASH: adapter exited %EIF_RC% before a decision; fail-closed
exit /b 2
