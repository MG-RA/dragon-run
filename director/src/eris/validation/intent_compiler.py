"""
Intent Compiler - Translates player intents into Minecraft events.

The player's tarot identity influences HOW the intent manifests:
- A Fool entering danger → reckless, takes damage
- A Magician entering danger → calculated, finds resources
- A Tower entering danger → brings chaos, spawns mobs
"""

import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .intents import Intent, IntentResult
from .player_state import Dimension, PlayerState
from .scenario_schema import (
    AdvancementEvent,
    ChatEvent,
    DamageEvent,
    DimensionChangeEvent,
    Event,
    HealthChangeEvent,
    InventoryEvent,
    ItemCraftedEvent,
    MobKillEvent,
    PortalPlacedEvent,
    StructureDiscoveryEvent,
)
from .tarot import TarotCard, TarotProfile

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .synthetic_world import SyntheticWorld


@dataclass
class CompilationContext:
    """Context needed for compiling intents to events."""

    player: PlayerState
    tarot: TarotProfile
    world: "SyntheticWorld"
    rng: random.Random


class IntentCompiler:
    """
    Compiles player intentions into scenario events.

    Tarot identity influences:
    - Event variations (damage, loot, chat)
    - Success rates
    - Side effects
    """

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def compile(
        self,
        intent_result: IntentResult,
        player: PlayerState,
        tarot: TarotProfile,
        world: "SyntheticWorld",
    ) -> list[Event]:
        """
        Convert an IntentResult into 1-5 Events.

        Args:
            intent_result: The decided intent with context
            player: Current player state
            tarot: Player's tarot profile
            world: Current world state

        Returns:
            List of events to apply
        """
        ctx = CompilationContext(
            player=player,
            tarot=tarot,
            world=world,
            rng=self.rng,
        )

        handler = INTENT_HANDLERS.get(intent_result.intent, self._handle_wait)
        return handler(self, ctx, intent_result)

    # ==================== EXPLORATION INTENTS ====================

    def _handle_explore(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Basic exploration - may find things."""
        events: list[Event] = []

        # Small chance to take environmental damage (falls, mobs)
        if ctx.tarot.dominant_card == TarotCard.FOOL and ctx.rng.random() < 0.15:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="fall",
                    amount=ctx.rng.randint(1, 4),
                )
            )

        # Small chance to find resources
        if ctx.rng.random() < 0.2:
            item = ctx.rng.choice(["coal", "iron_ore", "cobblestone", "oak_log"])
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="add",
                    item=item,
                    count=ctx.rng.randint(1, 3),
                )
            )

        return events

    def _handle_enter_danger(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Enter a dangerous area (dimension change).

        GATED ON WORLD CAPABILITIES:
        - Cannot enter nether without portal
        - Cannot enter end without end portal activated
        """
        events: list[Event] = []
        card = ctx.tarot.dominant_card
        caps = ctx.world.capabilities

        # Determine target dimension
        target_dim = intent.target_location or "nether"
        from_dim = ctx.player.dimension.value

        # ==================== CAPABILITY GATES ====================

        if target_dim == "nether":
            if not caps.can_enter_nether:
                # No portal exists - must work toward building one
                logger.debug(
                    f"[GATE] {ctx.player.name} cannot enter nether - no portal exists"
                )
                # Instead of entering, work toward portal
                return self._handle_work_toward_portal(ctx)

        elif target_dim in ("end", "the_end"):
            if not caps.can_enter_end:
                # End not accessible yet
                logger.debug(
                    f"[GATE] {ctx.player.name} cannot enter End - portal not ready"
                )
                # Work toward end access
                return self._handle_work_toward_end(ctx)

        # ==================== PORTAL EXISTS - CAN ENTER ====================

        # Add dimension change
        events.append(
            DimensionChangeEvent(
                player=ctx.player.name,
                from_dim=from_dim,
                to_dim=target_dim,
            )
        )

        # Tarot influences the transition
        if card == TarotCard.FOOL:
            # Fool rushes in recklessly - often takes damage
            if ctx.rng.random() < 0.5:
                events.append(
                    DamageEvent(
                        player=ctx.player.name,
                        source="lava" if target_dim == "nether" else "void",
                        amount=ctx.rng.randint(2, 6),
                    )
                )

        elif card == TarotCard.MAGICIAN:
            # Magician enters prepared - finds resources
            if ctx.rng.random() < 0.4:
                item = "gold_ingot" if target_dim == "nether" else "ender_pearl"
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item=item,
                        count=ctx.rng.randint(1, 3),
                    )
                )

        elif card == TarotCard.TOWER:
            # Tower brings chaos - aggros mobs, causes problems
            if ctx.rng.random() < 0.6:
                events.append(
                    ChatEvent(
                        player=ctx.player.name,
                        message="Watch out! I'm coming through!",
                    )
                )

        elif card == TarotCard.DEATH:
            # Death enters without hesitation, even at low HP
            # No extra events - just pure progression
            pass

        return events

    def _handle_work_toward_portal(
        self, ctx: CompilationContext
    ) -> list[Event]:
        """Work toward building a nether portal when one doesn't exist."""
        events: list[Event] = []
        caps = ctx.world.capabilities

        # Check what's needed for portal: obsidian source + flint_and_steel
        has_obsidian_source = caps.has_bucket or caps.has_diamond_pickaxe or caps.obsidian >= 10

        if not has_obsidian_source:
            # Need tools first - gather resources for obsidian
            if ctx.rng.random() < 0.3:
                # Find iron for bucket
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item="iron_ingot",
                        count=ctx.rng.randint(1, 3),
                    )
                )
            if ctx.rng.random() < 0.2:
                events.append(
                    ChatEvent(
                        player=ctx.player.name,
                        message="Need to find iron for a bucket...",
                    )
                )
        elif not caps.has_flint_and_steel:
            # Have obsidian source but need flint and steel to light
            if ctx.rng.random() < 0.4:
                events.append(
                    ItemCraftedEvent(
                        player=ctx.player.name,
                        item="flint_and_steel",
                        count=1,
                    )
                )
            else:
                events.append(
                    ChatEvent(
                        player=ctx.player.name,
                        message="Need flint and steel to light the portal...",
                    )
                )
        elif caps.can_build_portal:
            # Have everything - place the portal!
            events.append(
                PortalPlacedEvent(
                    player=ctx.player.name,
                    portal_type="nether",
                )
            )
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Portal is lit! Let's go!",
                )
            )

        return events

    def _handle_work_toward_end(
        self, ctx: CompilationContext
    ) -> list[Event]:
        """Work toward activating end portal when it's not ready."""
        events: list[Event] = []
        caps = ctx.world.capabilities

        # Check what's needed
        if caps.eyes_of_ender < 12:
            if caps.can_craft_eyes:
                # Craft eyes
                can_craft = min(caps.blaze_rods, caps.ender_pearls, 12 - caps.eyes_of_ender)
                if can_craft > 0:
                    events.append(
                        ItemCraftedEvent(
                            player=ctx.player.name,
                            item="eye_of_ender",
                            count=can_craft,
                        )
                    )
            elif not caps.can_farm_blazes:
                # Need to find fortress or enter nether
                events.append(
                    ChatEvent(
                        player=ctx.player.name,
                        message="Need blaze rods... where's the fortress?",
                    )
                )
            elif caps.blaze_rods == 0:
                # Farm blazes
                events.append(
                    MobKillEvent(
                        player=ctx.player.name,
                        mob_type="blaze",
                        count=1,
                    )
                )
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item="blaze_rod",
                        count=1,
                    )
                )

        elif not caps.stronghold_found:
            # Use eyes to find stronghold
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Following the eye...",
                )
            )
            if ctx.rng.random() < 0.3:
                events.append(
                    StructureDiscoveryEvent(
                        player=ctx.player.name,
                        structure="stronghold",
                    )
                )

        elif caps.stronghold_found and caps.eyes_of_ender >= 12:
            # Activate end portal
            events.append(
                PortalPlacedEvent(
                    player=ctx.player.name,
                    portal_type="end",
                )
            )

        return events

    def _handle_chase_rare(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Chase rare items or mobs."""
        events: list[Event] = []

        # Risk/reward based on tarot
        if ctx.tarot.dominant_card in (TarotCard.FOOL, TarotCard.DEATH):
            # Higher reward, higher risk
            if ctx.rng.random() < 0.3:
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item="diamond",
                        count=ctx.rng.randint(1, 2),
                    )
                )
            if ctx.rng.random() < 0.4:
                events.append(
                    DamageEvent(
                        player=ctx.player.name,
                        source="creeper",
                        amount=ctx.rng.randint(4, 8),
                    )
                )
        else:
            # Lower reward, lower risk
            if ctx.rng.random() < 0.2:
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item="gold_ingot",
                        count=ctx.rng.randint(1, 3),
                    )
                )

        return events

    def _handle_rush_structure(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Rush to find a structure.

        GATED ON WORLD CAPABILITIES:
        - Fortress requires nether access
        - Stronghold requires eyes of ender
        - Bastion requires nether access
        """
        events: list[Event] = []
        target = intent.target_location or "fortress"
        caps = ctx.world.capabilities

        # ==================== CAPABILITY GATES ====================

        if target == "fortress":
            if not caps.can_enter_nether:
                # Cannot find fortress without nether access
                logger.debug(
                    f"[GATE] {ctx.player.name} cannot rush fortress - not in nether"
                )
                return self._handle_work_toward_portal(ctx)
            if ctx.player.dimension != Dimension.NETHER:
                # Not in nether yet - need to enter first
                return self._handle_enter_danger(
                    ctx,
                    IntentResult(
                        intent=Intent.ENTER_DANGER,
                        target_location="nether",
                        confidence=1.0,
                    ),
                )

        elif target == "stronghold":
            if not caps.can_locate_stronghold:
                # Need eyes to find stronghold
                logger.debug(
                    f"[GATE] {ctx.player.name} cannot rush stronghold - no eyes"
                )
                return self._handle_work_toward_end(ctx)

        elif target == "bastion":
            if not caps.can_enter_nether:
                logger.debug(
                    f"[GATE] {ctx.player.name} cannot rush bastion - not in nether"
                )
                return self._handle_work_toward_portal(ctx)
            if ctx.player.dimension != Dimension.NETHER:
                return self._handle_enter_danger(
                    ctx,
                    IntentResult(
                        intent=Intent.ENTER_DANGER,
                        target_location="nether",
                        confidence=1.0,
                    ),
                )

        # ==================== CAN DISCOVER STRUCTURE ====================

        # Discovery event
        events.append(
            StructureDiscoveryEvent(
                player=ctx.player.name,
                structure=target,
            )
        )

        # Tarot influences what happens at the structure
        if ctx.tarot.dominant_card == TarotCard.FOOL:
            # Fool triggers traps or aggros mobs
            if ctx.rng.random() < 0.4:
                events.append(
                    DamageEvent(
                        player=ctx.player.name,
                        source="blaze" if target == "fortress" else "silverfish",
                        amount=ctx.rng.randint(3, 6),
                    )
                )

        elif ctx.tarot.dominant_card == TarotCard.HERMIT:
            # Hermit sets up a hidden camp
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Found it. Setting up here.",
                )
            )

        return events

    def _handle_scout(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Scout without engaging - safer exploration."""
        events: list[Event] = []

        # Small chance to discover structure
        if ctx.rng.random() < 0.15:
            structure = ctx.rng.choice(["village", "mineshaft", "ruined_portal"])
            events.append(
                StructureDiscoveryEvent(
                    player=ctx.player.name,
                    structure=structure,
                )
            )

        return events

    def _handle_flee(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Flee from danger."""
        events: list[Event] = []

        # May take damage while fleeing
        if ctx.rng.random() < 0.3:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="fall",
                    amount=ctx.rng.randint(1, 3),
                )
            )

        return events

    # ==================== BUILDING INTENTS ====================

    def _handle_build_base(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Build a base/shelter."""
        events: list[Event] = []

        # Use materials
        if ctx.player.inventory.get("cobblestone", 0) >= 10:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="cobblestone",
                    count=10,
                )
            )

        return events

    def _handle_secure_area(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Secure an area (light up, wall off)."""
        events: list[Event] = []

        # Use torches if available
        if ctx.player.inventory.get("torch", 0) >= 4:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="torch",
                    count=4,
                )
            )

        return events

    def _handle_build_farm(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Build a farm for resources."""
        events: list[Event] = []

        # Magician is efficient - gets more resources
        if ctx.tarot.dominant_card == TarotCard.MAGICIAN:
            if ctx.rng.random() < 0.5:
                events.append(
                    InventoryEvent(
                        player=ctx.player.name,
                        action="add",
                        item="iron_ingot",
                        count=ctx.rng.randint(2, 5),
                    )
                )

        return events

    def _handle_light_area(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Light up an area with torches."""
        return self._handle_secure_area(ctx, intent)

    def _handle_craft_optimal(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Craft optimal gear."""
        events: list[Event] = []

        # Convert raw materials to gear
        if ctx.player.inventory.get("iron_ingot", 0) >= 5:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="iron_ingot",
                    count=5,
                )
            )
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="add",
                    item="iron_chestplate",
                    count=1,
                )
            )

        return events

    def _handle_fortify(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Strengthen existing structures."""
        return self._handle_build_base(ctx, intent)

    # ==================== CONTROL INTENTS (Devil) ====================

    def _handle_hoard(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Collect and keep resources."""
        events: list[Event] = []

        # Find resources nearby
        if ctx.rng.random() < 0.4:
            item = ctx.rng.choice(["diamond", "gold_ingot", "iron_ingot", "blaze_rod"])
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="add",
                    item=item,
                    count=ctx.rng.randint(1, 2),
                )
            )

        # Devil hoards silently
        if ctx.tarot.dominant_card != TarotCard.DEVIL:
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Got some good stuff!",
                )
            )

        return events

    def _handle_control_portal(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Control portal access."""
        # No direct events - this is about positioning
        return []

    def _handle_withhold_resources(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Refuse to share resources."""
        # No direct events - behavioral
        return []

    def _handle_hide_chest(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Hide items in a chest."""
        # For simulation, items stay in inventory but are "hidden"
        return []

    def _handle_monopolize(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Control critical resources."""
        return self._handle_hoard(ctx, intent)

    # ==================== CHAOS INTENTS (Tower) ====================

    def _handle_grief(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Destroy others' work."""
        events: list[Event] = []

        if ctx.tarot.dominant_card == TarotCard.TOWER:
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Oops! Did I do that?",
                )
            )

        return events

    def _handle_trigger_mobs(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Aggro mobs toward players."""
        events: list[Event] = []

        # May take damage doing this
        if ctx.rng.random() < 0.3:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="zombie",
                    amount=ctx.rng.randint(2, 4),
                )
            )

        return events

    def _handle_lure_danger(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Lead enemies to others."""
        events: list[Event] = []

        events.append(
            ChatEvent(
                player=ctx.player.name,
                message="Run! They're coming!",
            )
        )

        return events

    def _handle_ignite(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Set fires, use TNT."""
        events: list[Event] = []

        # May cause self-damage
        if ctx.rng.random() < 0.25:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="fire",
                    amount=ctx.rng.randint(1, 3),
                )
            )

        return events

    def _handle_sabotage(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Break farms, traps, infrastructure."""
        return self._handle_grief(ctx, intent)

    # ==================== PROGRESSION INTENTS (Death) ====================

    def _handle_rush_endgame(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Rush toward dragon kill.

        GATED ON WORLD CAPABILITIES:
        - Cannot fight dragon without End access
        - Cannot enter End without portal activated
        """
        events: list[Event] = []
        caps = ctx.world.capabilities

        # ==================== CAPABILITY GATES ====================

        if not caps.can_enter_end:
            # Cannot reach dragon yet - work toward it
            logger.debug(
                f"[GATE] {ctx.player.name} cannot rush endgame - End not accessible"
            )
            return self._handle_work_toward_end(ctx)

        if ctx.player.dimension != Dimension.THE_END:
            # Have access but not in End yet - enter
            return self._handle_enter_danger(
                ctx,
                IntentResult(
                    intent=Intent.ENTER_DANGER,
                    target_location="end",
                    confidence=1.0,
                ),
            )

        # ==================== IN THE END - CAN FIGHT ====================

        # Fighting the dragon
        if ctx.rng.random() < 0.4:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="dragon",
                    amount=ctx.rng.randint(4, 10),
                )
            )

        # Progress toward killing dragon (represented as mob kill)
        events.append(
            MobKillEvent(
                player=ctx.player.name,
                mob_type="enderman",
                count=ctx.rng.randint(1, 3),
            )
        )

        return events

    def _handle_sacrifice(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Risk self for team progress."""
        events: list[Event] = []

        # Take damage to distract mobs
        events.append(
            DamageEvent(
                player=ctx.player.name,
                source="skeleton",
                amount=ctx.rng.randint(3, 6),
            )
        )

        events.append(
            ChatEvent(
                player=ctx.player.name,
                message="Go! I'll hold them!",
            )
        )

        return events

    def _handle_high_risk(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Take dangerous shortcuts."""
        events: list[Event] = []

        # High risk, high reward
        if ctx.rng.random() < 0.5:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="fall",
                    amount=ctx.rng.randint(4, 8),
                )
            )
        else:
            # Skip ahead in progression
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="add",
                    item="ender_pearl",
                    count=ctx.rng.randint(2, 4),
                )
            )

        return events

    def _handle_push_advancement(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Target specific advancements."""
        events: list[Event] = []

        # Generic advancement progress
        advancements = [
            "minecraft:story/mine_stone",
            "minecraft:story/iron_tools",
            "minecraft:nether/find_fortress",
        ]
        events.append(
            AdvancementEvent(
                player=ctx.player.name,
                advancement=ctx.rng.choice(advancements),
            )
        )

        return events

    def _handle_speedrun(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Optimize for time, ignore safety."""
        return self._handle_high_risk(ctx, intent)

    # ==================== SOCIAL INTENTS (Lovers, Star) ====================

    def _handle_follow_player(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Stay close to specific player."""
        # Positioning - no direct events
        return []

    def _handle_share_space(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Work in same area as others."""
        return []

    def _handle_trade(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Exchange resources with others."""
        events: list[Event] = []

        # Give away items
        if ctx.player.diamond_count > 0:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="diamond",
                    count=1,
                )
            )
            events.append(
                ChatEvent(
                    player=ctx.player.name,
                    message="Here, take this!",
                )
            )

        return events

    def _handle_rebuild(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Fix griefed/destroyed structures."""
        return self._handle_build_base(ctx, intent)

    def _handle_help_stragglers(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Assist players who fell behind."""
        events: list[Event] = []

        # Give food or items
        if ctx.player.inventory.get("cooked_beef", 0) > 0:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="cooked_beef",
                    count=1,
                )
            )

        return events

    def _handle_protect(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Shield others from danger."""
        events: list[Event] = []

        # May take damage protecting others
        if ctx.rng.random() < 0.3:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="zombie",
                    amount=ctx.rng.randint(2, 4),
                )
            )

        return events

    def _handle_rescue(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Save player in immediate danger."""
        events: list[Event] = []

        # Rush to help - may take damage
        if ctx.rng.random() < 0.4:
            events.append(
                DamageEvent(
                    player=ctx.player.name,
                    source="skeleton",
                    amount=ctx.rng.randint(2, 5),
                )
            )

        events.append(
            ChatEvent(
                player=ctx.player.name,
                message=f"I'm coming, {intent.target_player}!",
            )
        )

        return events

    # ==================== SURVIVAL INTENTS ====================

    def _handle_hide(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Go underground, avoid threats."""
        return []

    def _handle_return_to_player(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Regroup with team."""
        return []

    def _handle_rush_portal(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Emergency escape through portal."""
        events: list[Event] = []

        # Dimension change back to overworld
        if ctx.player.dimension != Dimension.OVERWORLD:
            events.append(
                DimensionChangeEvent(
                    player=ctx.player.name,
                    from_dim=ctx.player.dimension.value,
                    to_dim="overworld",
                )
            )

        return events

    def _handle_drop_items(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Sacrifice inventory to survive."""
        events: list[Event] = []

        # Drop heavy items to run faster (simulation)
        if ctx.player.inventory.get("cobblestone", 0) > 0:
            events.append(
                InventoryEvent(
                    player=ctx.player.name,
                    action="remove",
                    item="cobblestone",
                    count=min(32, ctx.player.inventory.get("cobblestone", 0)),
                )
            )

        return events

    def _handle_heal(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Eat food, use potions, regenerate."""
        events: list[Event] = []

        # Heal some health
        heal_amount = ctx.rng.randint(4, 8)
        events.append(
            HealthChangeEvent(
                player=ctx.player.name,
                amount=heal_amount,
            )
        )

        return events

    def _handle_retreat(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Tactical withdrawal."""
        return self._handle_flee(ctx, intent)

    # ==================== META INTENTS ====================

    def _handle_wait(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Do nothing, observe."""
        return []

    def _handle_plan(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """Pause to strategize."""
        return []

    def _handle_respond_to_eris(self, ctx: CompilationContext, intent: IntentResult) -> list[Event]:
        """React to Eris's actions."""
        events: list[Event] = []

        # Chat response
        responses = [
            "What was that?!",
            "Eris, please...",
            "Not again!",
            "Why?!",
            "I knew this would happen.",
        ]
        events.append(
            ChatEvent(
                player=ctx.player.name,
                message=ctx.rng.choice(responses),
            )
        )

        return events


# ==================== INTENT HANDLER MAP ====================

INTENT_HANDLERS: dict = {}


def _build_handler_map():
    """Build the intent -> handler map from IntentCompiler methods."""
    compiler = IntentCompiler()

    # Map intent enum values to handler methods
    handlers = {
        # Exploration
        Intent.EXPLORE: compiler._handle_explore,
        Intent.ENTER_DANGER: compiler._handle_enter_danger,
        Intent.CHASE_RARE: compiler._handle_chase_rare,
        Intent.RUSH_STRUCTURE: compiler._handle_rush_structure,
        Intent.SCOUT: compiler._handle_scout,
        Intent.FLEE: compiler._handle_flee,
        # Building
        Intent.BUILD_BASE: compiler._handle_build_base,
        Intent.SECURE_AREA: compiler._handle_secure_area,
        Intent.BUILD_FARM: compiler._handle_build_farm,
        Intent.LIGHT_AREA: compiler._handle_light_area,
        Intent.CRAFT_OPTIMAL: compiler._handle_craft_optimal,
        Intent.FORTIFY: compiler._handle_fortify,
        # Control
        Intent.HOARD: compiler._handle_hoard,
        Intent.CONTROL_PORTAL: compiler._handle_control_portal,
        Intent.WITHHOLD_RESOURCES: compiler._handle_withhold_resources,
        Intent.HIDE_CHEST: compiler._handle_hide_chest,
        Intent.MONOPOLIZE: compiler._handle_monopolize,
        # Chaos
        Intent.GRIEF: compiler._handle_grief,
        Intent.TRIGGER_MOBS: compiler._handle_trigger_mobs,
        Intent.LURE_DANGER: compiler._handle_lure_danger,
        Intent.IGNITE: compiler._handle_ignite,
        Intent.SABOTAGE: compiler._handle_sabotage,
        # Progression
        Intent.RUSH_ENDGAME: compiler._handle_rush_endgame,
        Intent.SACRIFICE: compiler._handle_sacrifice,
        Intent.HIGH_RISK: compiler._handle_high_risk,
        Intent.PUSH_ADVANCEMENT: compiler._handle_push_advancement,
        Intent.SPEEDRUN: compiler._handle_speedrun,
        # Social
        Intent.FOLLOW_PLAYER: compiler._handle_follow_player,
        Intent.SHARE_SPACE: compiler._handle_share_space,
        Intent.TRADE: compiler._handle_trade,
        Intent.REBUILD: compiler._handle_rebuild,
        Intent.HELP_STRAGGLERS: compiler._handle_help_stragglers,
        Intent.PROTECT: compiler._handle_protect,
        Intent.RESCUE: compiler._handle_rescue,
        # Survival
        Intent.HIDE: compiler._handle_hide,
        Intent.RETURN_TO_PLAYER: compiler._handle_return_to_player,
        Intent.RUSH_PORTAL: compiler._handle_rush_portal,
        Intent.DROP_ITEMS: compiler._handle_drop_items,
        Intent.HEAL: compiler._handle_heal,
        Intent.RETREAT: compiler._handle_retreat,
        # Meta
        Intent.WAIT: compiler._handle_wait,
        Intent.PLAN: compiler._handle_plan,
        Intent.RESPOND_TO_ERIS: compiler._handle_respond_to_eris,
    }

    return handlers


# Build on module load
INTENT_HANDLERS = _build_handler_map()
