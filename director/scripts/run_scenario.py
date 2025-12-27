"""Run a scenario through the closed-loop Eris harness.

This is the Phase 3 deliverable script:
One scenario → one full Eris run → full trace.

Usage:
    python scripts/run_scenario.py scenarios/01_simple_trio.yaml
    python scripts/run_scenario.py scenarios/02_nether_disaster.yaml --output results.json
    python scripts/run_scenario.py scenarios/ --batch  # Run all scenarios
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from langchain_ollama import ChatOllama

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.eris.validation import (
    ScenarioRunner,
    load_scenario,
    load_scenarios_from_directory,
    run_scenario_batch,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_single_scenario(
    scenario_path: Path,
    llm: ChatOllama,
    output_path: Path | None = None,
) -> None:
    """Run a single scenario and display results."""
    logger.info(f"Loading scenario: {scenario_path}")

    runner = ScenarioRunner(llm=llm, db=None)

    logger.info("Starting scenario run...")
    result = await runner.run_scenario(scenario_path)

    # Print summary
    print("\n" + "=" * 60)
    print("SCENARIO RUN COMPLETE")
    print("=" * 60)
    print(f"Scenario: {result.scenario_name}")
    print(f"Run ID: {result.run_id}")
    print(f"Success: {result.success}")
    if result.error:
        print(f"Error: {result.error}")
    print()
    print(f"Events processed: {result.total_events}")
    print(f"Eris interventions: {result.eris_interventions}")
    print(f"Tool calls executed: {result.total_tool_calls}")
    print()
    print(f"Final phase: {result.final_phase}")
    print(f"Final fracture: {result.final_fracture}")
    print()
    print(f"Victory: {result.victory}")
    print(f"Deaths: {result.deaths}")
    print()
    print(f"Duration: {result.duration_seconds:.2f} seconds")
    print("=" * 60)

    # Print Eris actions summary
    if result.eris_actions:
        print("\nERIS ACTIONS:")
        for i, action in enumerate(result.eris_actions, 1):
            print(f"  {i}. {action['command']} - {action['changes']} state changes")

    # Print graph outputs summary
    print(f"\nGRAPH OUTPUTS: {len(result.graph_outputs)} events processed")

    # Save to file if requested
    if output_path:
        logger.info(f"Saving results to: {output_path}")
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"\nResults saved to: {output_path}")

    print()


async def run_batch_scenarios(
    scenarios_dir: Path,
    llm: ChatOllama,
    output_path: Path | None = None,
) -> None:
    """Run all scenarios in a directory."""
    logger.info(f"Loading scenarios from: {scenarios_dir}")

    # Find all YAML files
    scenario_paths = list(scenarios_dir.glob("*.yaml"))
    logger.info(f"Found {len(scenario_paths)} scenarios")

    # Run batch
    results = await run_scenario_batch(scenario_paths, llm=llm, db=None)

    # Print summary table
    print("\n" + "=" * 80)
    print("BATCH RUN COMPLETE")
    print("=" * 80)
    print(f"{'Scenario':<30} {'Events':<8} {'Actions':<8} {'Victory':<8} {'Phase':<12}")
    print("-" * 80)

    for result in results:
        victory_str = "✓ Yes" if result.victory else "✗ No"
        print(
            f"{result.scenario_name:<30} "
            f"{result.total_events:<8} "
            f"{result.total_tool_calls:<8} "
            f"{victory_str:<8} "
            f"{result.final_phase:<12}"
        )

    print("=" * 80)

    # Print aggregate stats
    total_events = sum(r.total_events for r in results)
    total_actions = sum(r.total_tool_calls for r in results)
    total_victories = sum(1 for r in results if r.victory)
    total_duration = sum(r.duration_seconds for r in results)

    print()
    print(f"Total scenarios: {len(results)}")
    print(f"Total events: {total_events}")
    print(f"Total Eris actions: {total_actions}")
    print(f"Victories: {total_victories}/{len(results)}")
    print(f"Total duration: {total_duration:.2f}s")
    print()

    # Save to file if requested
    if output_path:
        logger.info(f"Saving batch results to: {output_path}")
        batch_dict = {
            "scenarios": [r.to_dict() for r in results],
            "summary": {
                "total_scenarios": len(results),
                "total_events": total_events,
                "total_actions": total_actions,
                "victories": total_victories,
                "total_duration": total_duration,
            },
        }
        with open(output_path, "w") as f:
            json.dump(batch_dict, f, indent=2, default=str)
        print(f"Batch results saved to: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run scenarios through Eris closed-loop harness (Phase 3)"
    )
    parser.add_argument(
        "scenario",
        type=Path,
        help="Path to scenario YAML file or directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output JSON file for results",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run all scenarios in directory (if scenario is a directory)",
    )
    parser.add_argument(
        "--model",
        default="ministral-3:14b",
        help="Ollama model to use (default: ministral-3:14b)",
    )
    parser.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Ollama host URL (default: http://localhost:11434)",
    )

    args = parser.parse_args()

    # Create LLM
    logger.info(f"Connecting to Ollama: {args.ollama_host} with model {args.model}")
    llm = ChatOllama(
        model=args.model,
        base_url=args.ollama_host,
        temperature=0.15,  # Recommended for ministral-3
        keep_alive="5m",
    )

    # Run scenario(s)
    if args.batch or args.scenario.is_dir():
        if not args.scenario.is_dir():
            logger.error("--batch requires a directory path")
            sys.exit(1)
        asyncio.run(run_batch_scenarios(args.scenario, llm, args.output))
    else:
        if not args.scenario.exists():
            logger.error(f"Scenario file not found: {args.scenario}")
            sys.exit(1)
        asyncio.run(run_single_scenario(args.scenario, llm, args.output))


if __name__ == "__main__":
    main()
