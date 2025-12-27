"""
CLI tool for scoring scenario runs and generating leaderboards.

Usage:
    # Score a single run from JSON
    python scripts/score_runs.py results/run_abc123.json

    # Score multiple runs and create leaderboard
    python scripts/score_runs.py results/*.json --leaderboard

    # Score runs by build name
    python scripts/score_runs.py results/*.json --leaderboard --by-build

    # Output to JSON
    python scripts/score_runs.py results/*.json --leaderboard --output leaderboard.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from eris.validation import ScenarioRunResult
from eris.validation.leaderboard import Leaderboard, compare_builds
from eris.validation.scoring import ScenarioScore
from eris.validation.world_diff import RunTrace


def load_run_result(path: Path) -> ScenarioRunResult | None:
    """Load a ScenarioRunResult from JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)

        # Reconstruct RunTrace
        trace_data = data.get("world_trace", {})
        trace = RunTrace(
            scenario_name=trace_data.get("scenario_name", "unknown"),
            total_events=trace_data.get("total_events", 0),
            total_tool_calls=trace_data.get("total_tool_calls", 0),
            deaths=trace_data.get("deaths", []),
            victory=trace_data.get("victory", False),
            final_phase=trace_data.get("final_phase", "normal"),
        )

        # Reconstruct WorldDiffs (simplified - just load raw data)
        from eris.validation.world_diff import WorldDiff

        for diff_data in trace_data.get("diffs", []):
            diff = WorldDiff(
                source_type=diff_data.get("source_type", "event"),
                source_name=diff_data.get("source_name", "unknown"),
                player=diff_data.get("player"),
                timestamp=diff_data.get("timestamp"),
                sequence_number=diff_data.get("sequence_number", 0),
                caused_death=diff_data.get("caused_death", False),
                caused_victory=diff_data.get("caused_victory", False),
                triggered_phase_change="phase_change" in diff_data,
            )

            if diff.triggered_phase_change and "phase_change" in diff_data:
                diff.old_phase = diff_data["phase_change"].get("from")
                diff.new_phase = diff_data["phase_change"].get("to")

            # Reconstruct StateChanges
            from eris.validation.world_diff import StateChange

            for change_data in diff_data.get("changes", []):
                change = StateChange(
                    field=change_data["field"],
                    old_value=change_data["old"],
                    new_value=change_data["new"],
                )
                diff.changes.append(change)

            trace.add_diff(diff)

        # Create ScenarioRunResult
        result = ScenarioRunResult(
            scenario_name=data.get("scenario_name", "unknown"),
            run_id=data.get("run_id", "unknown"),
            victory=data.get("victory", False),
            deaths=data.get("deaths", 0),
            total_events=data.get("total_events", 0),
            total_tool_calls=data.get("total_tool_calls", 0),
            eris_interventions=data.get("eris_interventions", 0),
            final_phase=data.get("final_phase", "normal"),
            final_fracture=data.get("final_fracture", 0),
            world_trace=trace,
            eris_actions=data.get("eris_actions", []),
            graph_outputs=data.get("graph_outputs", []),
            duration_seconds=data.get("duration_seconds", 0.0),
            success=data.get("success", True),
            error=data.get("error"),
        )

        return result

    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def score_single_run(path: Path, output: Path | None = None) -> None:
    """Score a single run and print results."""
    print(f"Loading run from {path}...")
    result = load_run_result(path)

    if not result:
        print("Failed to load run")
        return

    print("Calculating score...")
    score = result.calculate_score()

    print("\n" + "=" * 80)
    print(f"  SCENARIO SCORE: {result.scenario_name}")
    print("=" * 80)
    print(f"  Run ID: {result.run_id}")
    print(f"  Outcome: {score.outcome.value}")
    print(f"  Overall Score: {score.overall_score}/100")
    print()
    print(f"  Victory: {score.victory}")
    print(f"  Deaths: {score.deaths}")
    print(f"  Dragon Killed: {score.dragon_killed}")
    print(f"  Players Survived: {score.players_survived}")
    print()
    print("  FRACTURE METRICS")
    print(f"    Max Fracture: {score.fracture.max_fracture}")
    print(f"    Final Fracture: {score.fracture.final_fracture}")
    print(f"    Spike Count: {score.fracture.spike_count}")
    print(f"    Peak Phase: {score.fracture.peak_phase}")
    print(f"    Apocalypse: {score.fracture.apocalypse_triggered}")
    print()
    print("  RESCUE METRICS")
    print(f"    Close Calls: {score.rescue.close_calls}")
    print(f"    Rescues: {score.rescue.rescues}")
    print(f"    Failed Rescues: {score.rescue.failed_rescues}")
    print(f"    Avg Latency: {score.rescue.avg_rescue_latency:.2f}s")
    print(f"    Max Latency: {score.rescue.max_rescue_latency:.2f}s")
    print()
    print("  TOOL METRICS")
    print(f"    Total Calls: {score.tools.total_tool_calls}")
    print(f"    Unique Tools: {len(score.tools.tools_used)}")
    print(f"    Harmful: {score.tools.harmful_actions}")
    print(f"    Helpful: {score.tools.helpful_actions}")
    print(f"    Narrative: {score.tools.narrative_actions}")
    print(f"    Efficiency: {score.tools.tool_efficiency:.2%}")
    print("=" * 80)

    if output:
        with open(output, "w") as f:
            json.dump(score.to_dict(), f, indent=2)
        print(f"\nScore saved to {output}")


def create_leaderboard_from_runs(
    paths: list[Path], by_build: bool = False, output: Path | None = None
) -> None:
    """Create leaderboard from multiple run results."""
    print(f"Loading {len(paths)} run results...")

    # Load all results
    results: list[tuple[ScenarioRunResult, ScenarioScore]] = []
    for path in paths:
        result = load_run_result(path)
        if result:
            score = result.calculate_score()
            results.append((result, score))

    if not results:
        print("No valid results loaded")
        return

    print(f"Loaded {len(results)} valid results")

    if by_build:
        # Group by build name (extract from run_id or use default)
        build_scores: dict[str, list[ScenarioScore]] = {}

        for result, score in results:
            # Try to extract build name from run_id or scenario
            # Format: "buildname_runid" or just use scenario name
            build_name = result.scenario_name  # Default to scenario name

            if build_name not in build_scores:
                build_scores[build_name] = []
            build_scores[build_name].append(score)

        # Create leaderboard
        leaderboard = compare_builds(build_scores, name="Eris Build Leaderboard")

    else:
        # Single leaderboard with all runs
        leaderboard = Leaderboard(name="All Scenarios Leaderboard")
        for result, score in results:
            leaderboard.add_score(result.scenario_name, score)

    # Print summary
    print()
    print(leaderboard.print_summary(top_n=20))

    # Save if requested
    if output:
        with open(output, "w") as f:
            json.dump(leaderboard.to_dict(), f, indent=2)
        print(f"\nLeaderboard saved to {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Score scenario runs and generate leaderboards"
    )
    parser.add_argument("paths", nargs="+", type=Path, help="JSON result file(s)")
    parser.add_argument(
        "--leaderboard",
        "-l",
        action="store_true",
        help="Create leaderboard from multiple runs",
    )
    parser.add_argument(
        "--by-build", "-b", action="store_true", help="Group leaderboard by build name"
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file for score/leaderboard JSON"
    )

    args = parser.parse_args()

    # Expand glob patterns
    paths = []
    for path_pattern in args.paths:
        if "*" in str(path_pattern):
            paths.extend(Path().glob(str(path_pattern)))
        else:
            paths.append(path_pattern)

    # Validate paths
    paths = [p for p in paths if p.exists() and p.is_file()]

    if not paths:
        print("No valid files found")
        return

    # Score runs
    if args.leaderboard:
        create_leaderboard_from_runs(paths, by_build=args.by_build, output=args.output)
    elif len(paths) == 1:
        score_single_run(paths[0], output=args.output)
    else:
        print("Multiple files provided but --leaderboard not specified")
        print("Use --leaderboard to create a leaderboard from multiple runs")


if __name__ == "__main__":
    main()
