@echo off
setlocal
set "WCS_PLUGIN_ROOT=%~dp0.."
set "WCS_RUNTIME=%WCS_PLUGIN_ROOT%\scripts\runtime\windows-x64\wechat-studio.exe"
if exist "%WCS_RUNTIME%" (
  "%WCS_RUNTIME%" %*
  exit /b %ERRORLEVEL%
)

set "WCS_REPO_ROOT=%WCS_PLUGIN_ROOT%\..\.."
set "WCS_CORE_SRC=%WCS_REPO_ROOT%\packages\core\src"
set "WCS_CLI_SRC=%WCS_REPO_ROOT%\apps\cli\src"
if not exist "%WCS_CORE_SRC%\wechat_studio" (
  1>&2 echo ERROR WCS-RUNTIME-001: Bundled runtime is missing.
  exit /b 90
)

set "PYTHONPATH=%WCS_CORE_SRC%;%WCS_CLI_SRC%;%PYTHONPATH%"
if defined WECHAT_STUDIO_PYTHON (
  "%WECHAT_STUDIO_PYTHON%" -m wechat_studio_cli %*
  exit /b %ERRORLEVEL%
)
where python >nul 2>nul
if not errorlevel 1 (
  python -m wechat_studio_cli %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m wechat_studio_cli %*
  exit /b %ERRORLEVEL%
)
1>&2 echo ERROR WCS-RUNTIME-002: Source runtime requires Python or WECHAT_STUDIO_PYTHON.
exit /b 91
