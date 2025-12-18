package com.dragonrun.managers;

/**
 * Represents the current state of the Dragon Run game cycle.
 */
public enum GameState {
    /**
     * No active run. Players are in the lobby waiting.
     * Valid transitions: GENERATING
     */
    IDLE,

    /**
     * A new hardcore world is being generated.
     * Players remain in lobby during this phase.
     * Valid transitions: ACTIVE (on success), IDLE (on failure)
     */
    GENERATING,

    /**
     * An active run is in progress.
     * Players are in the hardcore world.
     * Valid transitions: RESETTING (on death/dragon kill)
     */
    ACTIVE,

    /**
     * Run has ended, world is being cleaned up.
     * Players are teleported to lobby, world is unloaded and deleted.
     * Valid transitions: IDLE
     */
    RESETTING
}
