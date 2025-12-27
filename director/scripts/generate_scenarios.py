#!/usr/bin/env python3
"""
CLI tool for generating and managing synthetic scenarios.

Usage:
    # Generate scenarios
    python scripts/generate_scenarios.py generate --count 10 --focus rescue_speed

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

from eris.validation import (
    DIFFICULTY_LEVELS,
    FOCUS_CATEGORIES,
    ScenarioFactory,
    validate_scenario_file,
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
    """Generate scenarios with filtering."""
    llm = setup_llm(args.model)
    factory = ScenarioFactory(
        llm=llm,
        scenarios_dir=args.output_dir,
        min_quality=args.min_quality,
    )

    logger.info(
        f"Generating {args.count} scenarios (focus={args.focus}, difficulty={args.difficulty})"
    )

    accepted, rejected = await factory.generate_and_filter(
        count=args.count,
        focus=args.focus,
        difficulty=args.difficulty,
    )

    # Display results
    print("\n" + "=" * 80)
    print("  GENERATION RESULTS")
    print("=" * 80)
    print(f"  Generated: {args.count}")
    print(f"  Accepted:  {len(accepted)}")
    print(f"  Rejected:  {len(rejected)}")
    print("=" * 80)

    if accepted:
        print(f"\n{'ACCEPTED SCENARIOS':^80}\n")
        for i, idea in enumerate(accepted, 1):
            print(f"{i}. {idea.name}")
            print(f"   Difficulty: {idea.difficulty}")
            print(f"   Focus: {', '.join(idea.focus_areas)}")
            print(f"   Events: {len(idea.key_events)}")
            print()

    if rejected and args.verbose:
        print(f"\n{'REJECTED SCENARIOS':^80}\n")
        for i, (idea, validation) in enumerate(rejected[:10], 1):  # Show first 10
            print(f"{i}. {idea.name}")
            print(f"   Quality: {validation.quality_score:.2f}")
            if validation.errors:
                print(f"   Errors: {', '.join(validation.errors[:2])}")
            if validation.warnings:
                print(f"   Warnings: {', '.join(validation.warnings[:2])}")
            print()

    # Save accepted scenarios
    if args.save and accepted:
        print(f"\n{'SAVING SCENARIOS':^80}\n")
        for idea in accepted:
            try:
                path = factory.save_scenario(idea)
                print(f"✓ Saved: {path.name}")
            except Exception as e:
                print(f"✗ Failed to save '{idea.name}': {e}")


async def cmd_library(args):
    """Generate a full scenario library."""
    llm = setup_llm(args.model)
    factory = ScenarioFactory(
        llm=llm,
        scenarios_dir=args.output_dir,
        min_quality=args.min_quality,
    )

    categories = args.categories.split(",") if args.categories else None

    logger.info(f"Generating scenario library: {args.total} scenarios")

    results = await factory.generate_library(
        total_scenarios=args.total,
        categories=categories,
    )

    # Display results
    print("\n" + "=" * 80)
    print("  SCENARIO LIBRARY GENERATION COMPLETE")
    print("=" * 80)
    print(f"  Total categories: {len(results)}")
    print(f"  Total scenarios:  {sum(len(paths) for paths in results.values())}")
    print("=" * 80)

    for category, paths in results.items():
        print(f"\n{category}: {len(paths)} scenarios")
        for path in paths:
            print(f"  - {path.name}")


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
    """Interactive curation mode."""
    llm = setup_llm(args.model)
    factory = ScenarioFactory(
        llm=llm,
        scenarios_dir=args.output_dir,
        min_quality=0.0,  # Accept all for curation
    )

    print("\n" + "=" * 80)
    print("  SCENARIO CURATION MODE")
    print("=" * 80)
    print(f"  Generating {args.count} scenarios for review")
    print("=" * 80)

    # Generate scenarios
    accepted, rejected = await factory.generate_and_filter(
        count=args.count,
        focus=args.focus,
    )

    all_scenarios = accepted + [idea for idea, _ in rejected]

    print(f"\nGenerated {len(all_scenarios)} scenarios. Review each:\n")

    approved = []
    for i, idea in enumerate(all_scenarios, 1):
        print("=" * 80)
        print(f"Scenario {i}/{len(all_scenarios)}: {idea.name}")
        print("=" * 80)
        print(f"Description: {idea.description}")
        print(f"Difficulty:  {idea.difficulty}")
        print(f"Party:       {idea.party}")
        print(f"Focus:       {', '.join(idea.focus_areas)}")
        print(f"Outcome:     {idea.expected_outcome}")
        print(f"\nKey Events ({len(idea.key_events)}):")
        for j, event in enumerate(idea.key_events, 1):
            print(f"  {j}. {event}")

        # Validate
        validation = factory.validate_scenario_idea(idea)
        print(f"\nQuality Score: {validation.quality_score:.2f}")
        if validation.warnings:
            print("Warnings:")
            for warning in validation.warnings:
                print(f"  - {warning}")

        # User decision
        print("\n" + "-" * 80)
        response = input("Accept this scenario? [y/N/q(uit)]: ").strip().lower()

        if response == "q":
            print("Quitting curation mode.")
            break
        elif response == "y":
            approved.append(idea)
            print("✓ Approved")
        else:
            print("✗ Rejected")

        print()

    # Save approved scenarios
    if approved:
        print("\n" + "=" * 80)
        print(f"  SAVING {len(approved)} APPROVED SCENARIOS")
        print("=" * 80)

        for idea in approved:
            path = factory.save_scenario(idea)
            print(f"✓ Saved: {path.name}")

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
