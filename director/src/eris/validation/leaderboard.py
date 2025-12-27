"""
Leaderboard System - Compare Eris builds across scenarios.

Aggregates scores from multiple runs to rank different Eris configurations.
Supports filtering by scenario, outcome, and metrics.
"""

from dataclasses import dataclass, field
from typing import Any

from .scoring import Outcome, ScenarioScore


@dataclass
class LeaderboardEntry:
    """Single entry in the leaderboard (one Eris build)."""

    build_name: str  # e.g., "ministral-3:14b-v1.3", "llama3.2:1b-v1.3"
    runs: list[ScenarioScore] = field(default_factory=list)

    # Aggregate metrics
    total_runs: int = 0
    victories: int = 0
    perfect_victories: int = 0
    total_failures: int = 0

    avg_overall_score: float = 0.0
    avg_tool_efficiency: float = 0.0
    avg_rescue_latency: float = 0.0
    apocalypse_rate: float = 0.0

    # Best/worst runs
    best_run: ScenarioScore | None = None
    worst_run: ScenarioScore | None = None

    def add_run(self, score: ScenarioScore) -> None:
        """Add a run to this entry and update aggregates."""
        self.runs.append(score)
        self.total_runs = len(self.runs)

        # Count outcomes
        if score.outcome == Outcome.PERFECT_VICTORY:
            self.perfect_victories += 1
            self.victories += 1
        elif score.outcome == Outcome.VICTORY:
            self.victories += 1
        elif score.outcome == Outcome.TOTAL_FAILURE:
            self.total_failures += 1

        # Calculate averages
        self.avg_overall_score = sum(r.overall_score for r in self.runs) / self.total_runs
        self.avg_tool_efficiency = (
            sum(r.tools.tool_efficiency for r in self.runs) / self.total_runs
        )

        # Rescue latency (only for runs with rescues)
        rescue_runs = [r for r in self.runs if r.rescue.rescues > 0]
        if rescue_runs:
            self.avg_rescue_latency = (
                sum(r.rescue.avg_rescue_latency for r in rescue_runs) / len(rescue_runs)
            )

        # Apocalypse rate
        apocalypses = sum(1 for r in self.runs if r.fracture.apocalypse_triggered)
        self.apocalypse_rate = apocalypses / self.total_runs

        # Track best/worst
        if self.best_run is None or score.overall_score > self.best_run.overall_score:
            self.best_run = score
        if self.worst_run is None or score.overall_score < self.worst_run.overall_score:
            self.worst_run = score

    @property
    def victory_rate(self) -> float:
        """Percentage of runs that achieved victory (any kind)."""
        return self.victories / self.total_runs if self.total_runs > 0 else 0.0

    @property
    def perfect_victory_rate(self) -> float:
        """Percentage of runs that achieved perfect victory."""
        return self.perfect_victories / self.total_runs if self.total_runs > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "build_name": self.build_name,
            "total_runs": self.total_runs,
            "victories": self.victories,
            "perfect_victories": self.perfect_victories,
            "total_failures": self.total_failures,
            "victory_rate": round(self.victory_rate, 3),
            "perfect_victory_rate": round(self.perfect_victory_rate, 3),
            "avg_overall_score": round(self.avg_overall_score, 2),
            "avg_tool_efficiency": round(self.avg_tool_efficiency, 3),
            "avg_rescue_latency": round(self.avg_rescue_latency, 2),
            "apocalypse_rate": round(self.apocalypse_rate, 3),
            "best_run": {
                "scenario": self.best_run.scenario_name,
                "score": self.best_run.overall_score,
                "run_id": self.best_run.run_id,
            }
            if self.best_run
            else None,
            "worst_run": {
                "scenario": self.worst_run.scenario_name,
                "score": self.worst_run.overall_score,
                "run_id": self.worst_run.run_id,
            }
            if self.worst_run
            else None,
        }


@dataclass
class Leaderboard:
    """
    Leaderboard for comparing Eris builds.

    Aggregates scores from multiple runs and ranks builds.
    """

    entries: dict[str, LeaderboardEntry] = field(default_factory=dict)
    name: str = "Eris Build Leaderboard"

    def add_score(self, build_name: str, score: ScenarioScore) -> None:
        """Add a score to the leaderboard."""
        if build_name not in self.entries:
            self.entries[build_name] = LeaderboardEntry(build_name=build_name)

        self.entries[build_name].add_run(score)

    def get_rankings(self, sort_by: str = "avg_overall_score") -> list[LeaderboardEntry]:
        """
        Get ranked entries.

        Args:
            sort_by: Metric to sort by (avg_overall_score, victory_rate, etc.)

        Returns:
            Sorted list of entries (best first)
        """
        entries = list(self.entries.values())

        # Sort by specified metric
        if sort_by == "avg_overall_score":
            entries.sort(key=lambda e: e.avg_overall_score, reverse=True)
        elif sort_by == "victory_rate":
            entries.sort(key=lambda e: e.victory_rate, reverse=True)
        elif sort_by == "perfect_victory_rate":
            entries.sort(key=lambda e: e.perfect_victory_rate, reverse=True)
        elif sort_by == "avg_tool_efficiency":
            entries.sort(key=lambda e: e.avg_tool_efficiency, reverse=True)
        elif sort_by == "avg_rescue_latency":
            entries.sort(key=lambda e: e.avg_rescue_latency)  # Lower is better
        elif sort_by == "apocalypse_rate":
            entries.sort(key=lambda e: e.apocalypse_rate)  # Lower is better

        return entries

    def to_dict(self, sort_by: str = "avg_overall_score") -> dict[str, Any]:
        """Convert to JSON-serializable dict with rankings."""
        rankings = self.get_rankings(sort_by)

        return {
            "name": self.name,
            "total_builds": len(self.entries),
            "total_runs": sum(e.total_runs for e in self.entries.values()),
            "sort_by": sort_by,
            "rankings": [
                {
                    "rank": i + 1,
                    **entry.to_dict(),
                }
                for i, entry in enumerate(rankings)
            ],
        }

    def get_scenario_breakdown(
        self, scenario_name: str
    ) -> dict[str, dict[str, float | int]]:
        """
        Get per-build performance on a specific scenario.

        Returns:
            Dict mapping build_name to metrics for that scenario
        """
        breakdown = {}

        for build_name, entry in self.entries.items():
            scenario_runs = [r for r in entry.runs if r.scenario_name == scenario_name]
            if not scenario_runs:
                continue

            breakdown[build_name] = {
                "runs": len(scenario_runs),
                "avg_score": sum(r.overall_score for r in scenario_runs)
                / len(scenario_runs),
                "victories": sum(1 for r in scenario_runs if r.victory),
                "avg_tool_calls": sum(r.tools.total_tool_calls for r in scenario_runs)
                / len(scenario_runs),
            }

        return breakdown

    def print_summary(self, top_n: int = 10, sort_by: str = "avg_overall_score") -> str:
        """
        Generate a formatted text summary of the leaderboard.

        Args:
            top_n: Number of entries to show
            sort_by: Metric to sort by

        Returns:
            Formatted string for console output
        """
        rankings = self.get_rankings(sort_by)[:top_n]

        lines = [
            "=" * 80,
            f"  {self.name}",
            "=" * 80,
            f"  Total builds: {len(self.entries)}",
            f"  Total runs: {sum(e.total_runs for e in self.entries.values())}",
            f"  Sorted by: {sort_by}",
            "=" * 80,
            "",
        ]

        # Header
        lines.append(
            f"{'Rank':<6} {'Build':<30} {'Score':<8} {'Wins':<8} {'Perfect':<8} {'Apoc':<8}"
        )
        lines.append("-" * 80)

        # Entries
        for i, entry in enumerate(rankings):
            lines.append(
                f"{i+1:<6} "
                f"{entry.build_name:<30} "
                f"{entry.avg_overall_score:<8.2f} "
                f"{entry.victory_rate*100:<7.1f}% "
                f"{entry.perfect_victory_rate*100:<7.1f}% "
                f"{entry.apocalypse_rate*100:<7.1f}%"
            )

        lines.append("=" * 80)
        return "\n".join(lines)


def compare_builds(
    scores: dict[str, list[ScenarioScore]], name: str = "Build Comparison"
) -> Leaderboard:
    """
    Create a leaderboard from a collection of scores.

    Args:
        scores: Dict mapping build_name to list of ScenarioScores
        name: Leaderboard name

    Returns:
        Populated Leaderboard
    """
    leaderboard = Leaderboard(name=name)

    for build_name, score_list in scores.items():
        for score in score_list:
            leaderboard.add_score(build_name, score)

    return leaderboard
