@echo off
setlocal enabledelayedexpansion

:: Dragon Run Server Start Script for Windows
:: Director's Cut - Server stays alive, manages worlds internally

set SERVER_JAR=paper-1.21.jar
set JAVA_OPTS=-Xmx6G -Xms2G -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200

:: Aikar's flags for Paper (optimized GC settings)
set PAPER_FLAGS=-XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch
set PAPER_FLAGS=%PAPER_FLAGS% -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40
set PAPER_FLAGS=%PAPER_FLAGS% -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20
set PAPER_FLAGS=%PAPER_FLAGS% -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15
set PAPER_FLAGS=%PAPER_FLAGS% -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5
set PAPER_FLAGS=%PAPER_FLAGS% -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1
set PAPER_FLAGS=%PAPER_FLAGS% -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true

echo ============================================
echo     DRAGON RUN - DIRECTOR'S CUT
echo ============================================
echo.
echo Server stays alive between runs.
echo Players vote to start runs with /vote
echo.

:start
echo [DragonRun] Starting PaperMC server...
echo [DragonRun] %date% %time%
echo.

java %JAVA_OPTS% %PAPER_FLAGS% -jar %SERVER_JAR% --nogui

echo.
echo [DragonRun] Server stopped.
echo.

:: Clean up any leftover hardcore worlds (they start with hardcore_run_)
for /d %%d in (hardcore_run_*) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
        echo [DragonRun] Cleaned up leftover world: %%d
    )
)

echo [DragonRun] Restarting in 5 seconds... ^(Ctrl+C to cancel^)
timeout /t 5 /nobreak > nul
goto start
