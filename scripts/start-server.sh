#!/bin/bash
# Dragon Run Server Start Script
# This script manages the server lifecycle and world resets

WORLD_DIRS="world world_nether world_the_end"
SERVER_JAR="paper-1.21.jar"
JAVA_OPTS="-Xmx6G -Xms2G -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200"

# Aikar's flags for Paper (optimized GC settings)
PAPER_FLAGS="-XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15"
PAPER_FLAGS="$PAPER_FLAGS -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5"
PAPER_FLAGS="$PAPER_FLAGS -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1"
PAPER_FLAGS="$PAPER_FLAGS -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true"

echo "============================================"
echo "       DRAGON RUN SERVER MANAGER"
echo "============================================"
echo ""

while true; do
    echo "[DragonRun] Starting PaperMC server..."
    echo "[DragonRun] $(date)"
    echo ""

    java $JAVA_OPTS $PAPER_FLAGS -jar $SERVER_JAR --nogui

    EXIT_CODE=$?
    echo ""
    echo "[DragonRun] Server stopped with exit code: $EXIT_CODE"

    if [ -f "RESET_TRIGGER" ]; then
        echo ""
        echo "============================================"
        echo "         WORLD RESET TRIGGERED"
        echo "============================================"
        echo ""

        # Read and display trigger info
        RESET_INFO=$(cat RESET_TRIGGER)
        echo "[DragonRun] Reset caused by: $RESET_INFO"
        echo ""

        # Delete world folders
        for dir in $WORLD_DIRS; do
            if [ -d "$dir" ]; then
                rm -rf "$dir"
                echo "[DragonRun] Deleted $dir"
            fi
        done

        # Remove trigger file
        rm RESET_TRIGGER

        echo ""
        echo "[DragonRun] World reset complete!"
        echo "[DragonRun] Restarting server in 5 seconds..."
        echo ""
        sleep 5
    else
        echo ""
        echo "[DragonRun] Server stopped without reset trigger."
        echo "[DragonRun] Restarting in 10 seconds... (Ctrl+C to cancel)"
        echo ""
        sleep 10
    fi
done
