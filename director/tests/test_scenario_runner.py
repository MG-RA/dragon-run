"""Tests for Phase 3: Closed-loop scenario runner.

Tests the complete flow:
Scenario → SyntheticEventProcessor → LangGraph → SyntheticGameStateClient → SyntheticWorld
"""

import asyncio
from pathlib import Path

import pytest
from langchain_ollama import ChatOllama

from eris.validation import (
    ScenarioRunner,
    ScenarioRunResult,
    SyntheticEventProcessor,
    SyntheticGameStateClient,
    SyntheticWorld,
    load_scenario,
)


@pytest.fixture
def scenarios_dir():
    """Get scenarios directory path."""
    return Path(__file__).parent.parent.parent / "scenarios"


@pytest.fixture
def simple_trio_scenario(scenarios_dir):
    """Load simple trio scenario."""
    return load_scenario(scenarios_dir / "01_simple_trio.yaml")


@pytest.fixture
def nether_disaster_scenario(scenarios_dir):
    """Load nether disaster scenario."""
    return load_scenario(scenarios_dir / "02_nether_disaster.yaml")


@pytest.fixture
def eris_chaos_scenario(scenarios_dir):
    """Load eris chaos scenario."""
    return load_scenario(scenarios_dir / "03_eris_chaos.yaml")


@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing (or real one if Ollama available)."""
    # Try to create real LLM, fall back to mock if unavailable
    try:
        return ChatOllama(
            model="llama3.2:1b",  # Smallest fast model
            base_url="http://localhost:11434",
            temperature=0.7,
        )
    except Exception:
        # Mock LLM that returns simple responses
        class MockLLM:
            async def ainvoke(self, messages):
                return "I observe silently."

        return MockLLM()


# === Test Event Processor ===


def test_event_processor_init(simple_trio_scenario):
    """Test SyntheticEventProcessor initialization."""
    processor = SyntheticEventProcessor(simple_trio_scenario)

    assert processor.scenario == simple_trio_scenario
    assert processor.event_index == 0
    assert processor.has_more_events()


def test_event_processor_iteration(simple_trio_scenario):
    """Test event processor iteration."""
    processor = SyntheticEventProcessor(simple_trio_scenario)

    events_processed = 0
    while processor.has_more_events():
        event = processor.get_next_event()
        assert event is not None
        assert "eventType" in event
        assert "data" in event
        events_processed += 1

    # Should match scenario event count
    assert events_processed == len(simple_trio_scenario.events)
    assert not processor.has_more_events()


def test_event_processor_reset(simple_trio_scenario):
    """Test event processor reset."""
    processor = SyntheticEventProcessor(simple_trio_scenario)

    # Process some events
    processor.get_next_event()
    processor.get_next_event()
    assert processor.event_index == 2

    # Reset
    processor.reset()
    assert processor.event_index == 0
    assert processor.has_more_events()


def test_event_conversion_advancement(simple_trio_scenario):
    """Test advancement event conversion."""
    processor = SyntheticEventProcessor(simple_trio_scenario)

    # First event should be advancement (mine_stone)
    event = processor.get_next_event()

    assert event["eventType"] == "advancement_made"
    assert "player" in event["data"]
    assert "advancementKey" in event["data"]
    assert event["data"]["advancementKey"].startswith("minecraft:")


def test_event_conversion_damage(nether_disaster_scenario):
    """Test damage event conversion."""
    processor = SyntheticEventProcessor(nether_disaster_scenario)

    # Find a damage event
    damage_event = None
    while processor.has_more_events():
        event = processor.get_next_event()
        if event["eventType"] == "player_damaged":
            damage_event = event
            break

    assert damage_event is not None
    assert "player" in damage_event["data"]
    assert "source" in damage_event["data"]
    assert "amount" in damage_event["data"]
    assert "finalHealth" in damage_event["data"]


def test_event_conversion_death(nether_disaster_scenario):
    """Test death event conversion."""
    processor = SyntheticEventProcessor(nether_disaster_scenario)

    # Last event should be death
    death_event = None
    while processor.has_more_events():
        event = processor.get_next_event()
        if event["eventType"] == "player_death":
            death_event = event

    assert death_event is not None
    assert "player" in death_event["data"]
    assert "cause" in death_event["data"]


# === Test Synthetic Client ===


def test_synthetic_client_init(simple_trio_scenario):
    """Test SyntheticGameStateClient initialization."""
    world = SyntheticWorld.from_scenario(simple_trio_scenario)
    client = SyntheticGameStateClient(world)

    assert client.world == world
    assert len(client.tool_calls) == 0
    assert len(client.correlation_ids) == 0


@pytest.mark.asyncio
async def test_synthetic_client_send_command(simple_trio_scenario):
    """Test sending commands via synthetic client."""
    world = SyntheticWorld.from_scenario(simple_trio_scenario)
    client = SyntheticGameStateClient(world)

    # Send a broadcast command
    correlation_id = await client.send_command("broadcast", {"message": "Test message"})

    assert correlation_id is not None
    assert len(client.tool_calls) == 1
    assert client.tool_calls[0]["command"] == "broadcast"
    assert client.tool_calls[0]["success"] is True


@pytest.mark.asyncio
async def test_synthetic_client_spawn_mob(simple_trio_scenario):
    """Test spawn_mob tool via client."""
    world = SyntheticWorld.from_scenario(simple_trio_scenario)
    client = SyntheticGameStateClient(world)

    initial_mob_count = len(world.spawned_mobs)

    # Spawn 3 zombies near Alice
    await client.send_command("spawn_mob", {
        "target": "Alice",
        "mob_type": "zombie",
        "count": 3,
    })

    assert len(world.spawned_mobs) == initial_mob_count + 3
    assert all(mob.mob_type == "zombie" for mob in world.spawned_mobs[-3:])


@pytest.mark.asyncio
async def test_synthetic_client_reset(simple_trio_scenario):
    """Test client reset."""
    world = SyntheticWorld.from_scenario(simple_trio_scenario)
    client = SyntheticGameStateClient(world)

    await client.send_command("broadcast", {"message": "Test"})
    assert len(client.tool_calls) == 1

    client.reset()
    assert len(client.tool_calls) == 0
    assert len(client.correlation_ids) == 0


# === Test Scenario Runner ===


@pytest.mark.asyncio
async def test_scenario_runner_simple_run(simple_trio_scenario, mock_llm):
    """Test running a simple scenario through the complete pipeline."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    result = await runner.run_scenario(simple_trio_scenario, run_id="test-001")

    # Check basic result structure
    assert isinstance(result, ScenarioRunResult)
    assert result.scenario_name == simple_trio_scenario.metadata.name
    assert result.run_id == "test-001"
    assert result.success is True

    # Check event processing
    assert result.total_events > 0
    assert result.total_events == len(simple_trio_scenario.events)

    # Check telemetry
    assert result.world_trace is not None
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_scenario_runner_death_scenario(nether_disaster_scenario, mock_llm):
    """Test running a death scenario."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    result = await runner.run_scenario(nether_disaster_scenario)

    assert result.success is True
    assert result.deaths >= 1  # Should have at least one death
    assert result.victory is False  # Run should fail


@pytest.mark.asyncio
async def test_scenario_runner_graph_outputs(simple_trio_scenario, mock_llm):
    """Test that graph outputs are captured."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    result = await runner.run_scenario(simple_trio_scenario)

    # Graph should output for each event
    assert len(result.graph_outputs) > 0

    # Check structure of graph outputs
    for output in result.graph_outputs:
        assert "event_type" in output
        assert "trace_id" in output
        assert "mask" in output
        assert "phase" in output
        assert "fracture" in output
        assert "decision" in output


@pytest.mark.asyncio
async def test_scenario_runner_eris_actions(eris_chaos_scenario, mock_llm):
    """Test that Eris actions are captured."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    result = await runner.run_scenario(eris_chaos_scenario)

    # Eris may or may not intervene depending on LLM
    # Just check structure is correct
    assert isinstance(result.eris_actions, list)
    assert result.total_tool_calls == len(result.eris_actions)

    # If there are actions, check structure
    for action in result.eris_actions:
        assert "command" in action
        assert "args" in action
        assert "timestamp" in action
        assert "success" in action


@pytest.mark.asyncio
async def test_scenario_runner_to_dict(simple_trio_scenario, mock_llm):
    """Test serialization to dict."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    result = await runner.run_scenario(simple_trio_scenario)
    result_dict = result.to_dict()

    # Check all required fields
    assert "scenario_name" in result_dict
    assert "run_id" in result_dict
    assert "victory" in result_dict
    assert "deaths" in result_dict
    assert "total_events" in result_dict
    assert "total_tool_calls" in result_dict
    assert "eris_interventions" in result_dict
    assert "final_phase" in result_dict
    assert "final_fracture" in result_dict
    assert "world_trace" in result_dict
    assert "eris_actions" in result_dict
    assert "graph_outputs" in result_dict
    assert "duration_seconds" in result_dict
    assert "success" in result_dict


@pytest.mark.asyncio
async def test_scenario_runner_from_path(scenarios_dir, mock_llm):
    """Test running scenario from path."""
    runner = ScenarioRunner(llm=mock_llm, db=None)

    scenario_path = scenarios_dir / "01_simple_trio.yaml"
    result = await runner.run_scenario(scenario_path)

    assert result.success is True
    assert result.scenario_name == "Simple Trio Speedrun"


# === Integration Test ===


@pytest.mark.asyncio
@pytest.mark.slow
async def test_full_pipeline_integration(scenarios_dir, mock_llm):
    """Test complete pipeline with real scenario file.

    This is the Phase 3 deliverable test:
    One scenario → one full Eris run → full trace
    """
    runner = ScenarioRunner(llm=mock_llm, db=None)

    scenario_path = scenarios_dir / "01_simple_trio.yaml"
    result = await runner.run_scenario(scenario_path, run_id="integration-test")

    # Verify complete trace
    assert result.success is True
    assert result.run_id == "integration-test"

    # Verify scenario events were processed
    assert result.total_events == 35  # Simple trio has 35 events

    # Verify world state was updated
    assert result.world_trace.total_events == 35

    # Verify graph was invoked for each event
    assert len(result.graph_outputs) == result.total_events

    # Verify trace has complete telemetry
    trace_dict = result.world_trace.to_dict()
    assert "total_events" in trace_dict
    assert "diffs" in trace_dict
    assert "victory" in trace_dict

    # Print summary
    print("\n=== Integration Test Summary ===")
    print(f"Scenario: {result.scenario_name}")
    print(f"Events processed: {result.total_events}")
    print(f"Eris interventions: {result.eris_interventions}")
    print(f"Tool calls: {result.total_tool_calls}")
    print(f"Final phase: {result.final_phase}")
    print(f"Final fracture: {result.final_fracture}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Victory: {result.victory}")
    print("================================\n")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
