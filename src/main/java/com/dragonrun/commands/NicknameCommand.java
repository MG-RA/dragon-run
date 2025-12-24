package com.dragonrun.commands;

import com.dragonrun.DragonRunPlugin;
import com.dragonrun.util.MessageUtil;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.papermc.paper.command.brigadier.CommandSourceStack;
import io.papermc.paper.command.brigadier.Commands;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.minimessage.MiniMessage;
import net.kyori.adventure.text.minimessage.tag.resolver.TagResolver;
import net.kyori.adventure.text.minimessage.tag.standard.StandardTags;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.entity.Player;

/**
 * Command for players to set custom display names with MiniMessage formatting.
 */
@SuppressWarnings("UnstableApiUsage")
public class NicknameCommand {

    private final DragonRunPlugin plugin;
    private static final int MAX_NICKNAME_LENGTH = 32;

    public NicknameCommand(DragonRunPlugin plugin) {
        this.plugin = plugin;
    }

    public void register(Commands commands) {
        commands.register(
            Commands.literal("nickname")
                .then(Commands.argument("name", StringArgumentType.greedyString())
                    .executes(ctx -> {
                        String nickname = StringArgumentType.getString(ctx, "name");
                        return executeSetNickname(ctx.getSource(), nickname);
                    })
                )
                .then(Commands.literal("reset")
                    .executes(ctx -> executeResetNickname(ctx.getSource()))
                )
                .build(),
            "Set a custom display name with MiniMessage formatting",
            java.util.List.of("nick", "name")
        );
    }

    private int executeSetNickname(CommandSourceStack source, String nicknameInput) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(MessageUtil.error("Only players can set nicknames."));
            return 0;
        }

        // Parse with MiniMessage
        MiniMessage mm = MiniMessage.builder()
            .tags(TagResolver.builder()
                .resolver(StandardTags.color())
                .resolver(StandardTags.decorations())
                .resolver(StandardTags.gradient())
                .resolver(StandardTags.rainbow())
                .build())
            .build();

        Component parsedNickname;
        try {
            parsedNickname = mm.deserialize(nicknameInput);
        } catch (Exception e) {
            player.sendMessage(MessageUtil.error("Invalid MiniMessage formatting: " + e.getMessage()));
            return 0;
        }

        // Check plain text length
        String plainText = PlainTextComponentSerializer.plainText().serialize(parsedNickname);
        if (plainText.isEmpty()) {
            player.sendMessage(MessageUtil.error("Nickname cannot be empty."));
            return 0;
        }
        if (plainText.length() > MAX_NICKNAME_LENGTH) {
            player.sendMessage(MessageUtil.error("Nickname too long (max " + MAX_NICKNAME_LENGTH + " characters)."));
            return 0;
        }

        // Set the display name
        player.displayName(parsedNickname);

        // Confirm
        Component message = Component.text()
            .append(Component.text("[DR] ", net.kyori.adventure.text.format.NamedTextColor.DARK_GRAY))
            .append(Component.text("Nickname set to: ", net.kyori.adventure.text.format.NamedTextColor.GRAY))
            .append(parsedNickname)
            .build();
        player.sendMessage(message);

        return 1;
    }

    private int executeResetNickname(CommandSourceStack source) {
        if (!(source.getSender() instanceof Player player)) {
            source.getSender().sendMessage(MessageUtil.error("Only players can reset nicknames."));
            return 0;
        }

        player.displayName(Component.text(player.getName()));
        player.sendMessage(MessageUtil.success("Nickname reset to " + player.getName()));
        return 1;
    }
}
