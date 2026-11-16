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

REM Interpreter lookup as in the Cursor launcher (BACKLOG-236 security fix):
REM with NoDefaultCurrentDirectoryInExePath set, cmd (and every process the
REM adapter and guard start) never runs a python.cmd, python.bat or git.exe
REM placed in the project root ahead of PATH. One built-in line checks that a
REM name exists on PATH; cmd then runs it by name in its own PATH and PATHEXT
REM order. No where.exe process, and nothing here reads the input pipe.
set "NoDefaultCurrentDirectoryInExePath=1"
REM With that setting cmd finds nothing when PATH starts with an empty entry,
REM so a leading empty entry becomes System32.
set "EIF_PATH_LEAD="
setlocal EnableDelayedExpansion
if "!PATH:~0,1!"==";" (endlocal & set "EIF_PATH_LEAD=1") else endlocal
if defined EIF_PATH_LEAD set "PATH=%SystemRoot%\System32%PATH%"
set "EIF_PYTHON="
set "EIF_PYTHON_ARGS="
set "EIF_EXTS=%PATHEXT%"
if not defined EIF_EXTS set "EIF_EXTS=.COM;.EXE;.BAT;.CMD"
for %%N in (python py python3) do if not defined EIF_PYTHON for %%E in ("%EIF_EXTS:;=" "%") do if not defined EIF_PYTHON for %%F in ("%%N%%~E") do if not "%%~$PATH:F"=="" set "EIF_PYTHON=%%N"
if "%EIF_PYTHON%"=="py" set "EIF_PYTHON_ARGS=-3"
if defined EIF_PYTHON goto :run
if not exist "%SystemRoot%\py.exe" goto :no_python
set "EIF_PYTHON="%SystemRoot%\py.exe""
set "EIF_PYTHON_ARGS=-3"
goto :run

:no_python
>&2 echo EIF claude-code adapter fault SHIM_NO_INTERPRETER: no Python interpreter found on PATH (tried python, py -3, python3)
exit /b 2

:run
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 "%SCRIPT%"
set "EIF_RC=%ERRORLEVEL%"
if "%EIF_RC%"=="0" exit /b 0
if "%EIF_RC%"=="2" exit /b 2
>&2 echo EIF claude-code adapter fault SHIM_LAUNCHER_CRASH: adapter exited %EIF_RC% before a decision; fail-closed
exit /b 2
