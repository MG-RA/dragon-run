package com.dragonrun.listeners;

import com.dragonrun.DragonRunPlugin;
import com.google.gson.JsonObject;
import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;

/**
 * Listens to chat messages and forwards them to the Director AI if enabled.
 */
public class DirectorChatListener implements Listener {

    private final DragonRunPlugin plugin;

    public DirectorChatListener(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onChat(AsyncChatEvent event) {
        if (event.isCancelled()) return;
        if (plugin.getDirectorServer() == null) return;
        if (!plugin.getConfig().getBoolean("director.monitor-chat", true)) return;

        String playerName = event.getPlayer().getName();
        String message = PlainTextComponentSerializer.plainText().serialize(event.message());

        // Broadcast as event to director
        JsonObject data = new JsonObject();
        data.addProperty("player", playerName);
        data.addProperty("message", message);
        data.addProperty("playerUuid", event.getPlayer().getUniqueId().toString());

        plugin.getDirectorServer().broadcastEvent("player_chat", data);
    }
}
