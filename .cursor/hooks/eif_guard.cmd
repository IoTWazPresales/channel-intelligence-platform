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

:prepare_capture
set "EIF_TRIES=0"
:allocate_capture
set /a EIF_TRIES+=1 >nul
if %EIF_TRIES% GTR 3 goto :capture_failed
set "EIF_CAPTURE_DIR=%EIF_ROOT%\.eif\runtime\hook-launcher\%RANDOM%-%RANDOM%-%RANDOM%"
if exist "%EIF_CAPTURE_DIR%" goto :allocate_capture
mkdir "%EIF_CAPTURE_DIR%" >nul 2>&1
if errorlevel 1 goto :capture_failed
set "EIF_CAPTURE=%EIF_CAPTURE_DIR%\response.json"
set "EIF_VALIDATION=%EIF_CAPTURE_DIR%\validated"
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 "%SCRIPT%" >"%EIF_CAPTURE%"
set "EIF_RC=%ERRORLEVEL%"
if "%EIF_RC%"=="0" goto :validate_response
if "%EIF_RC%"=="2" goto :validate_response
goto :python_failed

:validate_response
REM Exact marker proves validation ran; an empty/malformed shim cannot validate
REM itself merely by returning exit zero. Input pipe is never read twice.
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 -I -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); valid=isinstance(d,dict) and d.get('permission') in ('allow','deny') and d.get('decision_kind') in ('policy','harness_fault') and isinstance(d.get('reason_code'),str) and bool(d['reason_code']) and ((int(sys.argv[2])==2)==(d['permission']=='deny' and d['decision_kind']=='policy')); json.dumps(d,allow_nan=False); print('EIF_VALID' if valid else 'INVALID',end='')" "%EIF_CAPTURE%" "%EIF_RC%" <nul >"%EIF_VALIDATION%" 2>nul
if errorlevel 1 goto :python_failed
for %%I in ("%EIF_VALIDATION%") do if not "%%~zI"=="9" goto :python_failed
set "EIF_VALIDATED="
set /p "EIF_VALIDATED=" <"%EIF_VALIDATION%"
if not "%EIF_VALIDATED%"=="EIF_VALID" goto :python_failed
type "%EIF_CAPTURE%"
if errorlevel 1 goto :delivery_failed
call :cleanup
exit /b %EIF_RC%

:capture_failed
set "EIF_CAPTURE_DIR="
call :emit_static HOOK_LAUNCHER_ERROR
exit /b 0
:python_failed
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
del /q "%EIF_CAPTURE_DIR%\response.json" "%EIF_CAPTURE_DIR%\validated" >nul 2>&1
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
