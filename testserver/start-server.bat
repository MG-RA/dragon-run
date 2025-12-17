@echo off
setlocal enabledelayedexpansion

:: Dragon Run Server Start Script for Windows
:: This script manages the server lifecycle and world resets

set WORLD_DIRS=world world_nether world_the_end
set SERVER_JAR=paper-1.21.10-117.jar
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
echo        DRAGON RUN SERVER MANAGER
echo ============================================
echo.

:start
echo [DragonRun] Starting PaperMC server...
echo [DragonRun] %date% %time%
echo.

java %JAVA_OPTS% %PAPER_FLAGS% -jar %SERVER_JAR% --nogui

echo.
echo [DragonRun] Server stopped.

if exist "RESET_TRIGGER" (
    echo.
    echo ============================================
    echo          WORLD RESET TRIGGERED
    echo ============================================
    echo.

    :: Display trigger info
    echo [DragonRun] Reset caused by:
    type RESET_TRIGGER
    echo.

    :: Delete world folders
    for %%d in (%WORLD_DIRS%) do (
        if exist "%%d" (
            rmdir /s /q "%%d"
            echo [DragonRun] Deleted %%d
        )
    )

    :: Remove trigger file
    del RESET_TRIGGER

    echo.
    echo [DragonRun] World reset complete!
    echo [DragonRun] Restarting server in 5 seconds...
    echo.
    timeout /t 5 /nobreak > nul
) else (
    echo.
    echo [DragonRun] Server stopped without reset trigger.
    echo [DragonRun] Restarting in 10 seconds... ^(Ctrl+C to cancel^)
    echo.
    timeout /t 10 /nobreak > nul
)

goto start
