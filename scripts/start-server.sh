#!/bin/bash
# Dragon Run Server Start Script
# Director's Cut - Server stays alive, manages worlds internally

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
echo "    DRAGON RUN - DIRECTOR'S CUT"
echo "============================================"
echo ""
echo "Server stays alive between runs."
echo "Players vote to start runs with /vote"
echo ""

while true; do
    echo "[DragonRun] Starting PaperMC server..."
    echo "[DragonRun] $(date)"
    echo ""

    java $JAVA_OPTS $PAPER_FLAGS -jar $SERVER_JAR --nogui

    EXIT_CODE=$?
    echo ""
    echo "[DragonRun] Server stopped with exit code: $EXIT_CODE"
    echo ""

    # Clean up any leftover hardcore worlds
    for dir in hardcore_run_*; do
        if [ -d "$dir" ]; then
            rm -rf "$dir"
            echo "[DragonRun] Cleaned up leftover world: $dir"
        fi
    done

    echo "[DragonRun] Restarting in 5 seconds... (Ctrl+C to cancel)"
    sleep 5
done
