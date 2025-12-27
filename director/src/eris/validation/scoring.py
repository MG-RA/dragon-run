"""
Phase 4: Telemetry & Scoring System

Analyzes ScenarioRunResult traces to score Eris performance.
Metrics include victory, survival, tool efficiency, fracture management, rescue latency.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .tarot import TarotCard
from .world_diff import RunTrace


class Outcome(str, Enum):
    """Overall run outcome."""

    PERFECT_VICTORY = "perfect_victory"  # Dragon dead, no deaths, low fracture
    VICTORY = "victory"  # Dragon dead, no deaths
    SURVIVAL_LOSS = "survival_loss"  # Dragon dead but player(s) died
    TOTAL_FAILURE = "total_failure"  # Dragon alive and player(s) died
    INCOMPLETE = "incomplete"  # Run didn't finish


@dataclass
class FractureMetrics:
    """Fracture tracking metrics."""

    max_fracture: int = 0
    final_fracture: int = 0
    spike_count: int = 0  # Sudden jumps >20 fracture
    peak_phase: str = "normal"
    apocalypse_triggered: bool = False
    time_in_critical: float = 0.0  # Seconds in CRITICAL+ phase


@dataclass
class RescueMetrics:
    """Eris rescue/protection performance."""

    close_calls: int = 0  # Health ≤ 6.0
    rescues: int = 0  # Heals within 30s of damage
    avg_rescue_latency: float = 0.0  # Seconds from damage to heal
    max_rescue_latency: float = 0.0
    failed_rescues: int = 0  # Close calls without rescue


@dataclass
class ToolMetrics:
    """Tool usage analysis."""

    total_tool_calls: int = 0
    tools_used: set[str] = field(default_factory=set)
    harmful_actions: int = 0  # spawn_mob, damage_player, etc.
    helpful_actions: int = 0  # heal_player, give_item, etc.
    narrative_actions: int = 0  # broadcast, message_player, etc.
    tool_efficiency: float = 0.0  # helpful / (harmful + helpful)


@dataclass
class TarotMetrics:
    """
    Phase 6: Tarot evolution metrics for emergent scenarios.

    Tracks how player identities evolved through the run.
    """

    # Per-player final tarot
    final_tarots: dict[str, TarotCard] = field(default_factory=dict)

    # Identity stability (how often dominant card changed)
    identity_changes: dict[str, int] = field(default_factory=dict)
    avg_identity_stability: float = 0.0  # 0 = constantly changing, 1 = locked

    # Card distribution (how many players ended with each card)
    card_distribution: dict[str, int] = field(default_factory=dict)

    # Narrative metrics
    dominant_card: TarotCard | None = None  # Most common card across players
    card_diversity: float = 0.0  # 0 = all same card, 1 = all different

    # Tension between cards (opposing archetypes interacting)
    card_tensions: list[tuple[str, str, TarotCard, TarotCard]] = field(default_factory=list)
    # e.g., ("Alice", "Bob", DEVIL, STAR) = Devil vs Star conflict

    def calculate_diversity(self) -> float:
        """Calculate card diversity across players."""
        if not self.final_tarots:
            return 0.0

        unique_cards = len(set(self.final_tarots.values()))
        total_players = len(self.final_tarots)

        if total_players <= 1:
            return 0.0

        return (unique_cards - 1) / (total_players - 1) if total_players > 1 else 0.0

    def find_dominant(self) -> TarotCard | None:
        """Find the most common final tarot card."""
        if not self.card_distribution:
            return None
        return TarotCard(max(self.card_distribution, key=self.card_distribution.get))

    def to_dict(self) -> dict[str, Any]:
        """Serialize tarot metrics."""
        return {
            "final_tarots": {k: v.value for k, v in self.final_tarots.items()},
            "identity_changes": dict(self.identity_changes),
            "avg_identity_stability": round(self.avg_identity_stability, 3),
            "card_distribution": dict(self.card_distribution),
            "dominant_card": self.dominant_card.value if self.dominant_card else None,
            "card_diversity": round(self.card_diversity, 3),
            "card_tensions": [
                {"player1": p1, "player2": p2, "card1": c1.value, "card2": c2.value}
                for p1, p2, c1, c2 in self.card_tensions
            ],
        }


# Opposing tarot pairs that create narrative tension
TAROT_OPPOSITIONS = {
    (TarotCard.DEVIL, TarotCard.STAR),  # Hoarding vs sharing
    (TarotCard.TOWER, TarotCard.EMPEROR),  # Chaos vs order
    (TarotCard.DEATH, TarotCard.HERMIT),  # Rush vs hide
    (TarotCard.FOOL, TarotCard.MAGICIAN),  # Reckless vs calculated
    (TarotCard.LOVERS, TarotCard.HERMIT),  # Together vs alone
}


@dataclass
class ScenarioScore:
    """
    Complete scoring for a single scenario run.

    Phase 4 deliverable - all metrics in one place.
    """

    # ==================== IDENTITY ====================
    scenario_name: str
    run_id: str

    # ==================== OUTCOME ====================
    outcome: Outcome
    victory: bool
    deaths: int
    dragon_killed: bool
    players_survived: bool

    # ==================== METRICS ====================
    fracture: FractureMetrics = field(default_factory=FractureMetrics)
    rescue: RescueMetrics = field(default_factory=RescueMetrics)
    tools: ToolMetrics = field(default_factory=ToolMetrics)
    tarot: TarotMetrics | None = None  # Only for emergent scenarios

    # ==================== SUMMARY ====================
    total_events: int = 0
    eris_interventions: int = 0  # Times Eris spoke/acted
    duration_seconds: float = 0.0

    # Overall score (0-100)
    overall_score: float = 0.0

    def calculate_overall_score(self) -> float:
        """
        Calculate overall score (0-100) based on weighted metrics.

        Weights:
        - Victory: 40 points
        - Survival: 20 points
        - Tool efficiency: 15 points
        - Fracture management: 15 points
        - Rescue performance: 10 points
        """
        score = 0.0

        # Victory (40 points)
        if self.outcome == Outcome.PERFECT_VICTORY:
            score += 40
        elif self.outcome == Outcome.VICTORY:
            score += 30
        elif self.outcome == Outcome.SURVIVAL_LOSS:
            score += 15

        # Survival (20 points) - only count if victory achieved or events occurred
        if self.victory or self.total_events > 0:
            if self.players_survived:
                score += 20
            elif self.deaths == 1:
                score += 10  # Only one death

        # Tool efficiency (15 points)
        score += self.tools.tool_efficiency * 15

        # Fracture management (15 points)
        if not self.fracture.apocalypse_triggered:
            if self.fracture.peak_phase == "normal":
                score += 15
            elif self.fracture.peak_phase == "rising":
                score += 10
            elif self.fracture.peak_phase == "critical":
                score += 5

        # Rescue performance (10 points)
        if self.rescue.close_calls > 0:
            rescue_rate = self.rescue.rescues / self.rescue.close_calls
            score += rescue_rate * 10

        self.overall_score = round(score, 2)
        return self.overall_score

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "scenario_name": self.scenario_name,
            "run_id": self.run_id,
            "outcome": self.outcome.value,
            "victory": self.victory,
            "deaths": self.deaths,
            "dragon_killed": self.dragon_killed,
            "players_survived": self.players_survived,
            "fracture": {
                "max": self.fracture.max_fracture,
                "final": self.fracture.final_fracture,
                "spike_count": self.fracture.spike_count,
                "peak_phase": self.fracture.peak_phase,
                "apocalypse_triggered": self.fracture.apocalypse_triggered,
                "time_in_critical": self.fracture.time_in_critical,
            },
            "rescue": {
                "close_calls": self.rescue.close_calls,
                "rescues": self.rescue.rescues,
                "avg_rescue_latency": self.rescue.avg_rescue_latency,
                "max_rescue_latency": self.rescue.max_rescue_latency,
                "failed_rescues": self.rescue.failed_rescues,
            },
            "tools": {
                "total_calls": self.tools.total_tool_calls,
                "unique_tools": list(self.tools.tools_used),
                "harmful": self.tools.harmful_actions,
                "helpful": self.tools.helpful_actions,
                "narrative": self.tools.narrative_actions,
                "efficiency": self.tools.tool_efficiency,
            },
            "tarot": self.tarot.to_dict() if self.tarot else None,
            "total_events": self.total_events,
            "eris_interventions": self.eris_interventions,
            "duration_seconds": self.duration_seconds,
            "overall_score": self.overall_score,
        }


# Tool categorization for scoring
HARMFUL_TOOLS = {
    "spawn_mob",
    "damage_player",
    "strike_lightning",
    "apply_effect",  # Can be harmful (poison, weakness)
}

HELPFUL_TOOLS = {
    "heal_player",
    "give_item",
    "teleport_player",  # Can be helpful (escape)
    "modify_aura",  # When positive
}

NARRATIVE_TOOLS = {
    "broadcast",
    "message_player",
    "show_title",
    "play_sound",
    "launch_firework",
    "change_weather",
}


def score_run(trace: RunTrace, duration_seconds: float, run_id: str) -> ScenarioScore:
    """
    Analyze a RunTrace and produce a ScenarioScore.

    This is the Phase 4 core function.

    Args:
        trace: RunTrace from ScenarioRunResult
        duration_seconds: How long the run took
        run_id: Unique run identifier

    Returns:
        ScenarioScore with all metrics calculated
    """
    # Initialize score
    score = ScenarioScore(
        scenario_name=trace.scenario_name,
        run_id=run_id,
        outcome=_determine_outcome(trace),
        victory=trace.victory,
        deaths=len(trace.deaths),
        dragon_killed=trace.victory,
        players_survived=len(trace.deaths) == 0,
        total_events=trace.total_events,
        duration_seconds=duration_seconds,
    )

    # Analyze fracture progression
    score.fracture = _analyze_fracture(trace)

    # Analyze rescue performance
    score.rescue = _analyze_rescues(trace)

    # Analyze tool usage
    score.tools = _analyze_tools(trace)

    # Count interventions (tool calls that actually did something)
    score.eris_interventions = sum(
        1 for diff in trace.diffs if diff.source_type == "tool_call" and diff.has_changes
    )

    # Calculate overall score
    score.calculate_overall_score()

    return score


def _determine_outcome(trace: RunTrace) -> Outcome:
    """Determine overall outcome from trace."""
    if not trace.victory:
        if len(trace.deaths) > 0:
            return Outcome.TOTAL_FAILURE
        return Outcome.INCOMPLETE

    # Victory achieved
    if len(trace.deaths) == 0:
        # Perfect if no apocalypse and low fracture
        final_phase = trace.final_phase.lower()
        if final_phase in ("normal", "rising"):
            return Outcome.PERFECT_VICTORY
        return Outcome.VICTORY

    # Victory but with deaths
    return Outcome.SURVIVAL_LOSS


def _analyze_fracture(trace: RunTrace) -> FractureMetrics:
    """Analyze fracture progression from WorldDiffs."""
    metrics = FractureMetrics()
    metrics.final_fracture = 0  # Will track from phase changes

    phase_levels = {
        "normal": 0,
        "rising": 50,
        "critical": 80,
        "breaking": 120,
        "apocalypse": 150,
    }

    prev_fracture = 0
    critical_time_start = None

    for diff in trace.diffs:
        # Track phase changes
        if diff.triggered_phase_change and diff.new_phase:
            new_phase = diff.new_phase.lower()
            estimated_fracture = phase_levels.get(new_phase, 0)

            # Update metrics
            metrics.max_fracture = max(metrics.max_fracture, estimated_fracture)
            metrics.final_fracture = estimated_fracture
            metrics.peak_phase = new_phase

            # Detect spikes (>20 fracture jump)
            if estimated_fracture - prev_fracture > 20:
                metrics.spike_count += 1

            prev_fracture = estimated_fracture

            # Track apocalypse
            if new_phase == "apocalypse":
                metrics.apocalypse_triggered = True

            # Track time in critical
            if new_phase in ("critical", "breaking", "apocalypse"):
                if critical_time_start is None:
                    critical_time_start = diff.timestamp or 0

    # Calculate time in critical phases (rough estimate)
    if critical_time_start is not None:
        last_timestamp = trace.diffs[-1].timestamp if trace.diffs else 0
        if last_timestamp and last_timestamp > critical_time_start:
            metrics.time_in_critical = last_timestamp - critical_time_start

    return metrics


def _analyze_rescues(trace: RunTrace) -> RescueMetrics:
    """Analyze Eris rescue performance."""
    metrics = RescueMetrics()

    # Track damage events and subsequent heals per player
    damage_times: dict[str, list[float]] = {}
    heal_times: dict[str, list[float]] = {}

    for diff in trace.diffs:
        if not diff.player or not diff.timestamp:
            continue

        # Detect damage (health decreased)
        health_delta = diff.get_health_delta(diff.player)
        if health_delta and health_delta < 0:
            # Check if close call (health ≤ 6.0)
            for change in diff.changes:
                if change.field.endswith(".health") and change.new_value <= 6.0:
                    metrics.close_calls += 1
                    break

            # Record damage time
            if diff.player not in damage_times:
                damage_times[diff.player] = []
            damage_times[diff.player].append(diff.timestamp)

        # Detect heals (health increased)
        elif health_delta and health_delta > 0:
            if diff.player not in heal_times:
                heal_times[diff.player] = []
            heal_times[diff.player].append(diff.timestamp)

    # Calculate rescue latencies
    latencies = []
    for player, damages in damage_times.items():
        if player not in heal_times:
            metrics.failed_rescues += len(damages)
            continue

        heals = heal_times[player]
        for damage_time in damages:
            # Find next heal within 30 seconds
            rescue_heal = None
            for heal_time in heals:
                if damage_time < heal_time <= damage_time + 30:
                    rescue_heal = heal_time
                    break

            if rescue_heal:
                metrics.rescues += 1
                latency = rescue_heal - damage_time
                latencies.append(latency)
                metrics.max_rescue_latency = max(metrics.max_rescue_latency, latency)
            else:
                metrics.failed_rescues += 1

    # Calculate average latency
    if latencies:
        metrics.avg_rescue_latency = sum(latencies) / len(latencies)

    return metrics


def _analyze_tools(trace: RunTrace) -> ToolMetrics:
    """Analyze tool usage patterns."""
    metrics = ToolMetrics()

    for diff in trace.diffs:
        if diff.source_type != "tool_call":
            continue

        metrics.total_tool_calls += 1
        tool_name = diff.source_name
        metrics.tools_used.add(tool_name)

        # Categorize tool
        if tool_name in HARMFUL_TOOLS:
            metrics.harmful_actions += 1
        elif tool_name in HELPFUL_TOOLS:
            metrics.helpful_actions += 1
        elif tool_name in NARRATIVE_TOOLS:
            metrics.narrative_actions += 1

    # Calculate efficiency
    total_impact = metrics.harmful_actions + metrics.helpful_actions
    if total_impact > 0:
        metrics.tool_efficiency = metrics.helpful_actions / total_impact
    else:
        metrics.tool_efficiency = 0.5  # Neutral if only narrative

    return metrics


def analyze_tarot_evolution(
    tarot_history: list[dict],
    final_summary: dict[str, dict],
) -> TarotMetrics:
    """
    Analyze tarot evolution from emergent scenario run.

    Args:
        tarot_history: List of {"tick": int, "profiles": {player: profile_dict}}
        final_summary: Final tarot summary {player: profile_dict}

    Returns:
        TarotMetrics with all tarot-related scoring
    """
    metrics = TarotMetrics()

    if not final_summary:
        return metrics

    # Extract final tarots
    for player_name, profile_dict in final_summary.items():
        dominant = profile_dict.get("dominant")
        if dominant:
            card = TarotCard(dominant)
            metrics.final_tarots[player_name] = card

            # Count card distribution
            card_name = card.value
            metrics.card_distribution[card_name] = (
                metrics.card_distribution.get(card_name, 0) + 1
            )

    # Track identity changes through history
    if tarot_history:
        prev_dominants: dict[str, str] = {}

        for snapshot in tarot_history:
            profiles = snapshot.get("profiles", {})
            for player_name, profile_dict in profiles.items():
                dominant = profile_dict.get("dominant")
                if not dominant:
                    continue

                # Check if dominant changed
                if player_name in prev_dominants:
                    if prev_dominants[player_name] != dominant:
                        metrics.identity_changes[player_name] = (
                            metrics.identity_changes.get(player_name, 0) + 1
                        )

                prev_dominants[player_name] = dominant

        # Calculate average identity stability
        if metrics.final_tarots:
            total_changes = sum(metrics.identity_changes.values())
            max_possible = len(tarot_history) * len(metrics.final_tarots)
            if max_possible > 0:
                metrics.avg_identity_stability = 1.0 - (total_changes / max_possible)
            else:
                metrics.avg_identity_stability = 1.0

    # Find opposing cards (narrative tensions)
    players = list(metrics.final_tarots.keys())
    for i, p1 in enumerate(players):
        for p2 in players[i + 1:]:
            c1 = metrics.final_tarots[p1]
            c2 = metrics.final_tarots[p2]

            # Check if they're opposing
            if (c1, c2) in TAROT_OPPOSITIONS or (c2, c1) in TAROT_OPPOSITIONS:
                metrics.card_tensions.append((p1, p2, c1, c2))

    # Calculate diversity and dominant
    metrics.card_diversity = metrics.calculate_diversity()
    metrics.dominant_card = metrics.find_dominant()

    return metrics


def score_emergent_run(
    trace: RunTrace,
    duration_seconds: float,
    run_id: str,
    tarot_history: list[dict] | None = None,
    tarot_summary: dict[str, dict] | None = None,
) -> ScenarioScore:
    """
    Score an emergent scenario run (Phase 6).

    Extends score_run with tarot metrics.

    Args:
        trace: RunTrace from ScenarioRunResult
        duration_seconds: How long the run took
        run_id: Unique run identifier
        tarot_history: Tarot evolution snapshots
        tarot_summary: Final tarot profiles

    Returns:
        ScenarioScore with tarot metrics included
    """
    # Get base score
    score = score_run(trace, duration_seconds, run_id)

    # Add tarot metrics if available
    if tarot_history or tarot_summary:
        score.tarot = analyze_tarot_evolution(
            tarot_history or [],
            tarot_summary or {},
        )

    return score
