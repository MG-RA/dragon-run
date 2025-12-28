#!/usr/bin/env python3
"""
CLI tool for generating and managing synthetic scenarios.

Uses SimWorldService for generation with feedback loops - rejected scenarios
are automatically regenerated with LLM feedback until they pass validation.

Usage:
    # Generate scenarios with feedback loop (recommended)
    python scripts/generate_scenarios.py generate --count 10 --focus rescue_speed --save

    # Generate full library
    python scripts/generate_scenarios.py library --total 50

    # Validate existing scenarios
    python scripts/generate_scenarios.py validate

    # List scenarios
    python scripts/generate_scenarios.py list --filter medium

    # Interactive curation mode
    python scripts/generate_scenarios.py curate --count 5
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langchain_ollama import ChatOllama

from eris.core.tracing import init_tracing
from eris.validation import (
    DIFFICULTY_LEVELS,
    FOCUS_CATEGORIES,
    validate_scenario_file,
)
from eris.validation.sim_world_service import (
    ScenarioStatus,
    SimWorldService,
    SimWorldServiceConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def setup_llm(model: str = "ministral-3:14b") -> ChatOllama:
    """Initialize LLM for scenario generation."""
    logger.info(f"Initializing LLM: {model}")
    return ChatOllama(
        model=model,
        base_url="http://localhost:11434",
        temperature=0.7,
        format="",
    )


async def cmd_generate(args):
    """Generate scenarios with feedback loop.

    Uses SimWorldService which automatically regenerates rejected scenarios
    with LLM feedback until they pass validation (up to max_retries attempts).
    """
    # Initialize tracing
    init_tracing()

    llm = setup_llm(args.model)
    config = SimWorldServiceConfig(
        max_retry_attempts=args.max_retries,
        min_quality_score=args.min_quality,
        scenarios_dir=args.output_dir,
    )
    service = SimWorldService(llm=llm, config=config)

    logger.info(
        f"Generating {args.count} scenarios with feedback loop "
        f"(focus={args.focus}, difficulty={args.difficulty}, max_retries={args.max_retries})"
    )

    # Use orchestrate_batch for multiple scenarios
    results = await service.orchestrate_batch(
        count=args.count,
        focus=args.focus,
        difficulty=args.difficulty,
        save=args.save,
        run=False,  # Don't run scenarios, just generate and save
    )

    # Count results
    accepted = [r for r in results if r.status in (
        ScenarioStatus.ACCEPTED, ScenarioStatus.SAVED, ScenarioStatus.COMPLETED
    )]
    rejected = [r for r in results if r.status == ScenarioStatus.REJECTED]
    failed = [r for r in results if r.status == ScenarioStatus.FAILED]
    total_attempts = sum(r.total_attempts for r in results)

    # Display results
    print("\n" + "=" * 80)
    print("  GENERATION RESULTS (with feedback loop)")
    print("=" * 80)
    print(f"  Requested:       {args.count}")
    print(f"  Accepted:        {len(accepted)}")
    print(f"  Rejected:        {len(rejected)}")
    print(f"  Failed:          {len(failed)}")
    print(f"  Total attempts:  {total_attempts}")
    print(f"  Avg attempts:    {total_attempts / args.count:.1f}")
    print("=" * 80)

    if accepted:
        print(f"\n{'ACCEPTED SCENARIOS':^80}\n")
        for i, result in enumerate(accepted, 1):
            idea = result.final_idea
            if idea:
                print(f"{i}. {idea.name}")
                print(f"   Difficulty: {idea.difficulty}")
                print(f"   Focus: {', '.join(idea.focus_areas)}")
                if result.final_validation:
                    print(f"   Quality: {result.final_validation.quality_score:.2f}")
                print(f"   Attempts: {result.total_attempts}")
                print(f"   Trace ID: {result.root_trace_id}")
                if result.saved_path:
                    print(f"   Saved: {result.saved_path.name}")
                print()

    if (rejected or failed) and args.verbose:
        print(f"\n{'REJECTED/FAILED SCENARIOS':^80}\n")
        for i, result in enumerate(rejected + failed, 1):
            idea = result.final_idea
            if idea:
                print(f"{i}. {idea.name}")
                print(f"   Quality: {result.final_validation.quality_score:.2f}" if result.final_validation else "   Quality: N/A")
                print(f"   Attempts: {result.total_attempts}")
                if result.error:
                    print(f"   Error: {result.error}")
                # Show last attempt's feedback
                if result.attempts and result.attempts[-1].feedback:
                    print("   Last feedback:")
                    for line in result.attempts[-1].feedback.split("\n")[:3]:
                        print(f"     {line}")
            print()


async def cmd_library(args):
    """Generate a full scenario library across multiple focus categories."""
    # Initialize tracing
    init_tracing()

    llm = setup_llm(args.model)
    config = SimWorldServiceConfig(
        max_retry_attempts=args.max_retries,
        min_quality_score=args.min_quality,
        scenarios_dir=args.output_dir,
    )
    service = SimWorldService(llm=llm, config=config)

    categories = args.categories.split(",") if args.categories else FOCUS_CATEGORIES
    scenarios_per_category = max(1, args.total // len(categories))

    logger.info(
        f"Generating scenario library: {args.total} scenarios across {len(categories)} categories"
    )

    all_results = {}
    total_accepted = 0
    total_attempts = 0

    for category in categories:
        logger.info(f"Generating {scenarios_per_category} scenarios for '{category}'")

        results = await service.orchestrate_batch(
            count=scenarios_per_category,
            focus=category,
            save=True,
            run=False,
        )

        accepted = [r for r in results if r.status in (
            ScenarioStatus.ACCEPTED, ScenarioStatus.SAVED
        )]
        all_results[category] = accepted
        total_accepted += len(accepted)
        total_attempts += sum(r.total_attempts for r in results)

    # Display results
    print("\n" + "=" * 80)
    print("  SCENARIO LIBRARY GENERATION COMPLETE")
    print("=" * 80)
    print(f"  Total categories: {len(all_results)}")
    print(f"  Total accepted:   {total_accepted}")
    print(f"  Total attempts:   {total_attempts}")
    print("=" * 80)

    for category, results in all_results.items():
        print(f"\n{category}: {len(results)} scenarios")
        for result in results:
            if result.saved_path:
                print(f"  - {result.saved_path.name}")


def cmd_validate(args):
    """Validate existing scenarios."""
    scenarios_dir = Path(args.scenarios_dir)

    if not scenarios_dir.exists():
        print(f"Error: Scenarios directory not found: {scenarios_dir}")
        return

    scenarios = sorted(scenarios_dir.glob("*.yaml"))

    if not scenarios:
        print(f"No scenarios found in {scenarios_dir}")
        return

    logger.info(f"Validating {len(scenarios)} scenarios")

    results = []
    for scenario_path in scenarios:
        validation = validate_scenario_file(scenario_path)
        results.append((scenario_path, validation))

    # Display results
    print("\n" + "=" * 80)
    print("  VALIDATION RESULTS")
    print("=" * 80)
    print(f"  Total scenarios: {len(scenarios)}")
    print(
        f"  Valid:           {sum(1 for _, v in results if v.valid)} ({sum(1 for _, v in results if v.valid) / len(results) * 100:.1f}%)"
    )
    print(
        f"  Average quality: {sum(v.quality_score for _, v in results) / len(results):.2f}"
    )
    print("=" * 80)

    # Show details
    if args.verbose:
        print(f"\n{'SCENARIO DETAILS':^80}\n")
        for path, validation in results:
            status = "✓ VALID" if validation.valid else "✗ INVALID"
            print(f"{status} {path.name}")
            print(f"  Quality: {validation.quality_score:.2f}")

            if validation.errors:
                print("  Errors:")
                for error in validation.errors:
                    print(f"    - {error}")

            if validation.warnings:
                print("  Warnings:")
                for warning in validation.warnings[:3]:  # First 3
                    print(f"    - {warning}")

            print()

    # Summary by quality tier
    print(f"\n{'QUALITY DISTRIBUTION':^80}\n")
    excellent = sum(1 for _, v in results if v.quality_score >= 0.9)
    good = sum(1 for _, v in results if 0.7 <= v.quality_score < 0.9)
    acceptable = sum(1 for _, v in results if 0.5 <= v.quality_score < 0.7)
    poor = sum(1 for _, v in results if v.quality_score < 0.5)

    print(f"  Excellent (0.9+): {excellent}")
    print(f"  Good (0.7-0.9):   {good}")
    print(f"  Acceptable (0.5-0.7): {acceptable}")
    print(f"  Poor (<0.5):      {poor}")


def cmd_list(args):
    """List scenarios with optional filtering."""
    scenarios_dir = Path(args.scenarios_dir)

    if not scenarios_dir.exists():
        print(f"Error: Scenarios directory not found: {scenarios_dir}")
        return

    scenarios = sorted(scenarios_dir.glob("*.yaml"))

    if not scenarios:
        print(f"No scenarios found in {scenarios_dir}")
        return

    # Apply filters
    if args.filter:
        filter_lower = args.filter.lower()
        scenarios = [s for s in scenarios if filter_lower in s.name.lower()]

    print("\n" + "=" * 80)
    print(f"  SCENARIOS ({len(scenarios)} found)")
    print("=" * 80)

    for i, scenario_path in enumerate(scenarios, 1):
        print(f"{i:3}. {scenario_path.name}")

        if args.verbose:
            validation = validate_scenario_file(scenario_path)
            print(f"     Quality: {validation.quality_score:.2f}")
            print(f"     Valid:   {'Yes' if validation.valid else 'No'}")


async def cmd_curate(args):
    """Interactive curation mode with feedback loop generation."""
    # Initialize tracing
    init_tracing()

    llm = setup_llm(args.model)
    config = SimWorldServiceConfig(
        max_retry_attempts=args.max_retries,
        min_quality_score=0.0,  # Accept all for curation (human reviews)
        scenarios_dir=args.output_dir,
    )
    service = SimWorldService(llm=llm, config=config)

    print("\n" + "=" * 80)
    print("  SCENARIO CURATION MODE")
    print("=" * 80)
    print(f"  Generating {args.count} scenarios for review")
    print("=" * 80)

    # Generate scenarios using feedback loop
    results = await service.orchestrate_batch(
        count=args.count,
        focus=args.focus,
        save=False,  # Don't save yet - human will decide
        run=False,
    )

    print(f"\nGenerated {len(results)} scenarios. Review each:\n")

    approved = []
    for i, result in enumerate(results, 1):
        idea = result.final_idea
        if not idea:
            continue

        print("=" * 80)
        print(f"Scenario {i}/{len(results)}: {idea.name}")
        print("=" * 80)
        print(f"Description: {idea.description}")
        print(f"Difficulty:  {idea.difficulty}")
        print(f"Party:       {idea.party}")
        print(f"Focus:       {', '.join(idea.focus_areas)}")
        print(f"Outcome:     {idea.expected_outcome}")
        print(f"\nKey Events ({len(idea.key_events)}):")
        for j, event in enumerate(idea.key_events, 1):
            print(f"  {j}. {event}")

        # Show validation info
        if result.final_validation:
            print(f"\nQuality Score: {result.final_validation.quality_score:.2f}")
            if result.final_validation.warnings:
                print("Warnings:")
                for warning in result.final_validation.warnings:
                    print(f"  - {warning}")

        print(f"\nGeneration attempts: {result.total_attempts}")
        print(f"Trace ID: {result.root_trace_id}")

        # User decision
        print("\n" + "-" * 80)
        response = input("Accept this scenario? [y/N/q(uit)]: ").strip().lower()

        if response == "q":
            print("Quitting curation mode.")
            break
        elif response == "y":
            approved.append(result)
            print("✓ Approved")
        else:
            print("✗ Rejected")

        print()

    # Save approved scenarios
    if approved:
        print("\n" + "=" * 80)
        print(f"  SAVING {len(approved)} APPROVED SCENARIOS")
        print("=" * 80)

        for result in approved:
            saved_result = await service.save_scenario(result)
            if saved_result.saved_path:
                print(f"✓ Saved: {saved_result.saved_path.name}")

        print(f"\nCuration complete: {len(approved)} scenarios saved")


def main():
    parser = argparse.ArgumentParser(
        description="Generate and manage synthetic Eris scenarios"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate scenarios")
    gen_parser.add_argument(
        "--count", type=int, default=10, help="Number of scenarios to generate"
    )
    gen_parser.add_argument(
        "--focus",
        choices=FOCUS_CATEGORIES,
        help="Focus area for scenarios",
    )
    gen_parser.add_argument(
        "--difficulty",
        choices=DIFFICULTY_LEVELS,
        help="Difficulty level",
    )
    gen_parser.add_argument(
        "--model", default="ministral-3:14b", help="Ollama model to use"
    )
    gen_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scenarios"),
        help="Output directory",
    )
    gen_parser.add_argument(
        "--min-quality",
        type=float,
        default=0.6,
        help="Minimum quality score (0.0-1.0)",
    )
    gen_parser.add_argument(
        "--save", action="store_true", help="Save accepted scenarios"
    )
    gen_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max regeneration attempts per scenario (default: 3)",
    )
    gen_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show rejected scenarios"
    )

    # Library command
    lib_parser = subparsers.add_parser("library", help="Generate scenario library")
    lib_parser.add_argument(
        "--total", type=int, default=50, help="Total scenarios to generate"
    )
    lib_parser.add_argument(
        "--categories",
        help="Comma-separated list of focus categories (default: all)",
    )
    lib_parser.add_argument(
        "--model", default="ministral-3:14b", help="Ollama model to use"
    )
    lib_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scenarios"),
        help="Output directory",
    )
    lib_parser.add_argument(
        "--min-quality",
        type=float,
        default=0.6,
        help="Minimum quality score",
    )
    lib_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max regeneration attempts per scenario (default: 3)",
    )

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate scenarios")
    val_parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=Path("scenarios"),
        help="Scenarios directory",
    )
    val_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed results"
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List scenarios")
    list_parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=Path("scenarios"),
        help="Scenarios directory",
    )
    list_parser.add_argument("--filter", help="Filter by name substring")
    list_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show details"
    )

    # Curate command
    curate_parser = subparsers.add_parser(
        "curate", help="Interactive curation mode"
    )
    curate_parser.add_argument(
        "--count", type=int, default=5, help="Number of scenarios to review"
    )
    curate_parser.add_argument(
        "--focus",
        choices=FOCUS_CATEGORIES,
        help="Focus area",
    )
    curate_parser.add_argument(
        "--model", default="ministral-3:14b", help="Ollama model to use"
    )
    curate_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scenarios"),
        help="Output directory",
    )
    curate_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max regeneration attempts per scenario (default: 3)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run command
    if args.command == "generate":
        asyncio.run(cmd_generate(args))
    elif args.command == "library":
        asyncio.run(cmd_library(args))
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "curate":
        asyncio.run(cmd_curate(args))


if __name__ == "__main__":
    main()
