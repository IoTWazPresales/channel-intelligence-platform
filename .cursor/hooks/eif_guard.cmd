:; exec /bin/sh "$(dirname -- "$0")/eif_guard.sh" "$@"; exit 126 #
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "SCRIPT=%~dp0eif_guard.py"
set "EIF_CAPTURE_DIR="
set "EIF_RC=0"
if defined CURSOR_PROJECT_DIR goto :project_root
set "EIF_ROOT=%CD%"
goto :find_python
:project_root
set "EIF_ROOT=%CURSOR_PROJECT_DIR%"

:find_python
REM Lookup never consumes Cursor's input pipe. CALL preserves control when the
REM selected executable is a batch shim. No child bytes reach Cursor yet.
"%SystemRoot%\System32\where.exe" python <nul >nul 2>&1
if not errorlevel 1 goto :select_python
"%SystemRoot%\System32\where.exe" py <nul >nul 2>&1
if not errorlevel 1 goto :select_py
"%SystemRoot%\System32\where.exe" python3 <nul >nul 2>&1
if not errorlevel 1 goto :select_python3
REM Cursor hook PATH is often System32-only; py.exe still lives in %SystemRoot%.
if exist "%SystemRoot%\py.exe" goto :select_py_root
call :emit_static HOOK_LAUNCHER_ERROR
exit /b 0

:select_python
set "EIF_PYTHON=python"
set "EIF_PYTHON_ARGS="
goto :prepare_capture
:select_py
set "EIF_PYTHON=py"
set "EIF_PYTHON_ARGS=-3"
goto :prepare_capture
:select_python3
set "EIF_PYTHON=python3"
set "EIF_PYTHON_ARGS="
goto :prepare_capture
:select_py_root
set "EIF_PYTHON=%SystemRoot%\py.exe"
set "EIF_PYTHON_ARGS=-3"

:prepare_capture
set "EIF_TRIES=0"
:allocate_capture
REM Launches started together share one clock-seeded %RANDOM% sequence. The
REM directory is used only by the launch whose mkdir created it; a lost claim
REM takes the next name, so each round admits at least one more launch.
set /a EIF_TRIES+=1 >nul
if %EIF_TRIES% GTR 64 goto :capture_failed
set "EIF_CAPTURE_DIR=%EIF_ROOT%\.eif\runtime\hook-launcher\%RANDOM%-%RANDOM%-%RANDOM%"
mkdir "%EIF_CAPTURE_DIR%" >nul 2>&1
if errorlevel 1 goto :allocate_capture
set "EIF_CAPTURE=%EIF_CAPTURE_DIR%\response.json"
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 "%SCRIPT%" >"%EIF_CAPTURE%"
set "EIF_RC=%ERRORLEVEL%"
if "%EIF_RC%"=="0" goto :validate_response
if "%EIF_RC%"=="2" goto :validate_response
goto :python_failed

:validate_response
REM Exact marker proves validation ran; an empty/malformed shim cannot validate
REM itself merely by returning exit zero. Input pipe is never read twice.
REM Validation only reads the captured response, so it may repeat. A scanner
REM can briefly hold a just-written file (sharing violation, size still 0).
REM Retries back off. A marker without a newline made set /p drop the line.
REM A response that stays invalid still fails closed; validator stderr is kept.
set "EIF_VTRIES=0"
:validate_attempt
set /a EIF_VTRIES+=1 >nul
if %EIF_VTRIES% GTR 8 goto :python_failed
if %EIF_VTRIES% GTR 1 call %EIF_PYTHON% %EIF_PYTHON_ARGS% -c "import time; time.sleep(0.05)" <nul >nul 2>&1
set "EIF_VALIDATION=%EIF_CAPTURE_DIR%\validated-%EIF_VTRIES%"
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 -I -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); valid=isinstance(d,dict) and d.get('permission') in ('allow','deny') and d.get('decision_kind') in ('policy','harness_fault') and isinstance(d.get('reason_code'),str) and bool(d['reason_code']) and ((int(sys.argv[2])==2)==(d['permission']=='deny' and d['decision_kind']=='policy')); json.dumps(d,allow_nan=False); sys.stdout.write('EIF_VALID\n' if valid else 'INVALID\n')" "%EIF_CAPTURE%" "%EIF_RC%" <nul >"%EIF_VALIDATION%" 2>"%EIF_CAPTURE_DIR%\validate.err"
if errorlevel 1 goto :validate_attempt
findstr /x /c:"EIF_VALID" "%EIF_VALIDATION%" >nul
if errorlevel 1 goto :validate_attempt
type "%EIF_CAPTURE%"
if errorlevel 1 goto :delivery_failed
call :cleanup
exit /b %EIF_RC%

:capture_failed
set "EIF_CAPTURE_DIR="
call :emit_static HOOK_LAUNCHER_ERROR
exit /b 0
:python_failed
if defined EIF_CAPTURE_DIR if exist "%EIF_CAPTURE_DIR%\validate.err" type "%EIF_CAPTURE_DIR%\validate.err" >>"%EIF_ROOT%\.eif\hook-guard.log"
call :cleanup
call :emit_static HOOK_INTERNAL_ERROR
exit /b 0
:delivery_failed
REM Never concatenate fallback after stdout delivery may have begun.
call :cleanup
>&2 echo EIF harness fault HOOK_EMIT_FAILURE: validated response could not be delivered
exit /b 1

:cleanup
if not defined EIF_CAPTURE_DIR goto :eof
del /q "%EIF_CAPTURE_DIR%\response.json" "%EIF_CAPTURE_DIR%\validated-*" "%EIF_CAPTURE_DIR%\validate.err" >nul 2>&1
rd "%EIF_CAPTURE_DIR%" >nul 2>&1
goto :eof

:emit_static
REM Inline fixed JSON stays valid when an installed static file is damaged.
if not exist "%EIF_ROOT%\.eif" mkdir "%EIF_ROOT%\.eif" >nul 2>&1
call :clear_error
>>"%EIF_ROOT%\.eif\hook-guard.log" echo {"decision_kind":"harness_fault","reason_code":"%~1","permission":"deny"} && goto :log_written
REM A failed redirection can leave ERRORLEVEL unchanged; use command success.
>&2 echo EIF harness fault HOOK_LOG_FAILURE: launcher could not write hook-guard.log
:log_written
>&2 echo EIF harness fault %~1: launcher could not obtain a valid permission decision
echo {"permission":"deny","decision_kind":"harness_fault","reason_code":"%~1","user_message":"%~1: guard launcher failed","agent_message":"EIF harness fault: launcher could not obtain a valid permission decision; repair before retrying"}
goto :eof

:clear_error
exit /b 0
