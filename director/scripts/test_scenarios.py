#!/usr/bin/env python3
"""
Test scenario loading and validation.

Tests Phase 1 deliverable: load_scenario() → validated event stream.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from eris.validation.scenario_loader import (
    ScenarioValidationError,
    load_scenario,
    load_scenarios_from_directory,
)


def test_individual_scenarios():
    """Test loading individual scenario files."""
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios"

    if not scenarios_dir.exists():
        print(f"[ERROR] Scenarios directory not found: {scenarios_dir}")
        return False

    print("=" * 60)
    print("Testing Individual Scenarios")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for yaml_file in sorted(scenarios_dir.glob("*.yaml")):
        print(f"\n[FILE] {yaml_file.name}")
        print("-" * 60)

        try:
            scenario = load_scenario(yaml_file)

            # Print scenario info
            print(f"  Name:        {scenario.metadata.name}")
            print(f"  Description: {scenario.metadata.description}")
            print(f"  Difficulty:  {scenario.metadata.difficulty}")
            print(f"  Players:     {len(scenario.party)}")
            print(f"  Events:      {len(scenario.events)}")

            # Get player names
            player_names = scenario.get_player_names()
            if player_names:
                print(f"  Party:       {', '.join(player_names)}")

            # Event type breakdown
            event_types = {}
            for event in scenario.events:
                event_type = event.type
                event_types[event_type] = event_types.get(event_type, 0) + 1

            print(f"  Event types: {dict(sorted(event_types.items()))}")

            # Check for special events
            has_death = any(e.type == "death" for e in scenario.events)
            has_dragon = any(e.type == "dragon_kill" for e in scenario.events)

            if has_death:
                print("  [WARN] Contains death event (run failure)")
            if has_dragon:
                print("  [DRAGON] Contains dragon kill (victory)")

            print(f"  [OK] VALID")
            success_count += 1

        except ScenarioValidationError as e:
            print(f"  [FAIL] VALIDATION FAILED: {e}")
            # Check if this is expected to fail
            if "invalid" in yaml_file.name.lower():
                print(f"  [INFO] (Expected failure for test scenario)")
                success_count += 1
            else:
                fail_count += 1

        except Exception as e:
            print(f"  [ERROR] {e}")
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"Results: {success_count} passed, {fail_count} failed")
    print("=" * 60)

    return fail_count == 0


def test_directory_loading():
    """Test bulk loading from directory."""
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios"

    if not scenarios_dir.exists():
        print(f"[ERROR] Scenarios directory not found: {scenarios_dir}")
        return False

    print("\n" + "=" * 60)
    print("Testing Directory Bulk Load")
    print("=" * 60)

    try:
        scenarios = load_scenarios_from_directory(scenarios_dir)
        print(f"\n[OK] Loaded {len(scenarios)} valid scenarios from {scenarios_dir.name}/")

        for scenario in scenarios:
            print(f"  - {scenario.metadata.name}")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to load directory: {e}")
        return False


def test_expected_failure():
    """Test that invalid scenarios are properly rejected."""
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios"
    invalid_file = scenarios_dir / "04_invalid_progression.yaml"

    if not invalid_file.exists():
        print(f"[INFO] Invalid test scenario not found, skipping: {invalid_file.name}")
        return True

    print("\n" + "=" * 60)
    print("Testing Expected Validation Failure")
    print("=" * 60)
    print(f"\n[FILE] {invalid_file.name}")

    try:
        scenario = load_scenario(invalid_file)
        print(f"[FAIL] Invalid scenario was accepted (should have failed)")
        return False

    except ScenarioValidationError as e:
        print(f"[OK] PASS: Correctly rejected invalid scenario")
        print(f"   Reason: {e}")
        return True

    except Exception as e:
        print(f"[ERROR] Unexpected exception: {e}")
        return False


def main():
    """Run all scenario tests."""
    print("\n[TEST] Scenario Validation Test Suite")
    print("Phase 1 Deliverable: load_scenario() -> validated event stream\n")

    results = []

    # Test 1: Individual scenario loading
    results.append(("Individual Scenarios", test_individual_scenarios()))

    # Test 2: Directory bulk loading
    results.append(("Directory Bulk Load", test_directory_loading()))

    # Test 3: Expected failure detection
    results.append(("Expected Failure", test_expected_failure()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "[OK] PASS" if passed else "[FAIL]"
        print(f"{status} - {test_name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print("\n[FAIL] Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
