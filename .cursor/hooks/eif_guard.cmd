:; exec /bin/sh "$(dirname -- "$0")/eif_guard.sh" "$@"; exit 126 #
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "SCRIPT=%~dp0eif_guard.py"
set "EIF_CAPTURE_DIR="
set "EIF_RC=0"
REM BACKLOG-236: tells the guard its host timeout is 30 s (watchdog 25 s).
set "EIF_HOOK_HOST=cursor"
if defined CURSOR_PROJECT_DIR goto :project_root
set "EIF_ROOT=%CD%"
goto :find_python
:project_root
set "EIF_ROOT=%CURSOR_PROJECT_DIR%"

:find_python
REM No where.exe process (about 1.5 s per call on a loaded machine) and no
REM search of the current directory: with NoDefaultCurrentDirectoryInExePath
REM set, cmd (and CreateProcess in the guard) no longer run a python.cmd or
REM git.exe placed in the project root ahead of PATH. One built-in line checks
REM that a name exists on PATH; cmd then runs it by name in its own PATH and
REM PATHEXT order, as before. A batch PATH walk was tried and dropped: cmd
REM re-reads the batch file for every executed line, and with 80 PATH entries
REM that cost more than where.exe under load. Nothing here reads the input pipe.
set "NoDefaultCurrentDirectoryInExePath=1"
REM With that setting cmd finds nothing at all when PATH starts with an empty
REM entry (measured: ";C:\Python314" fails, a middle or trailing ";;" works),
REM so a leading empty entry becomes System32. Delayed expansion reads the
REM first character without parsing PATH text as commands.
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
if defined EIF_PYTHON goto :prepare_capture
REM Cursor hook PATH is often System32-only; py.exe still lives in %SystemRoot%.
if not exist "%SystemRoot%\py.exe" goto :no_python
set "EIF_PYTHON="%SystemRoot%\py.exe""
set "EIF_PYTHON_ARGS=-3"
goto :prepare_capture
:no_python
call :emit_static HOOK_LAUNCHER_ERROR
exit /b 0

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
REM One interpreter runs the guard, then validates the reply bytes it captured.
REM The bootstrap below is launcher code, not guard code. It compiles the guard
REM from source as before (the guard, like its helpers, never runs from cached
REM bytecode), runs it as __main__, and only after the guard exits (or its
REM watchdog fires) reads response.json back from disk. It exits 100 or 102,
REM the guard exit code plus 100, only when the file holds exactly one JSON
REM object with permission allow/deny, decision_kind policy/harness_fault, a
REM non-empty reason_code, no NaN/Infinity, and exit 2 if and only if the
REM decision is a policy deny. The checks are expressions, not asserts, so
REM PYTHONOPTIMIZE cannot remove them. A scanner can briefly hold the file
REM (sharing violation, size still 0), so a failed read is retried 8 times.
REM The result travels in the exit code, not a file: cmd cannot retry a read
REM without starting a process.
REM Readable source: tools/launcher_boot.py; tools/gen_launcher_boot.py --check.
set "EIF_BOOT=exec('''import sys\nsys.path[:] = [p for p in sys.path if p not in ('', '.')]\nimport json, threading, time\n_EIFL = sys.argv[1:3]\nsys.argv = [_EIFL[0]]\n__file__ = _EIFL[0]\n_EIFL_LOCK = threading.Lock()\n_EIFL_SEEN = []\ndef _EIF_LAUNCHER_FINISH(rc):\n with _EIFL_LOCK:\n  if _EIFL_SEEN: return _EIFL_SEEN[0]\n  code = 1 if rc in (100, 102) else rc\n  if rc in (0, 2):\n   try: sys.stdout.flush()\n   except Exception: pass\n   for _ in range(8):\n    try:\n     with open(_EIFL[1], encoding='utf-8') as f: d = json.load(f)\n     ok = (isinstance(d, dict) and d.get('permission') in ('allow', 'deny')\n      and d.get('decision_kind') in ('policy', 'harness_fault')\n      and isinstance(d.get('reason_code'), str) and bool(d['reason_code'])\n      and (rc == 2) == (d['permission'] == 'deny' and d['decision_kind'] == 'policy'))\n     json.dumps(d, allow_nan=False)\n    except Exception: ok = False\n    if ok:\n     code = 100 + rc\n     break\n    time.sleep(0.05)\n  _EIFL_SEEN.append(code)\n  return code\ntry:\n exec(compile(open(_EIFL[0], 'rb').read(), _EIFL[0], 'exec'))\n _EIFL_RC = 0\nexcept SystemExit as e:\n _EIFL_RC = 0 if e.code is None else e.code if type(e.code) is int else 1\n if _EIFL_RC == 1 and type(e.code) is not int: print(e.code, file=sys.stderr)\nraise SystemExit(_EIF_LAUNCHER_FINISH(_EIFL_RC))''')"
call %EIF_PYTHON% %EIF_PYTHON_ARGS% -u -X utf8 -c "%EIF_BOOT%" "%SCRIPT%" "%EIF_CAPTURE%" >"%EIF_CAPTURE%"
set "EIF_RC=%ERRORLEVEL%"
REM Only a validated reply is delivered. A raw 0 or 2 comes from something that
REM did not validate (a shim that ignores its arguments, an exit before the
REM check) and fails closed like any other code.
if "%EIF_RC%"=="100" (set "EIF_RC=0" & goto :deliver)
if "%EIF_RC%"=="102" (set "EIF_RC=2" & goto :deliver)
goto :python_failed

:deliver
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
del /q "%EIF_CAPTURE_DIR%\response.json" >nul 2>&1
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
