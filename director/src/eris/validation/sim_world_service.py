"""
SimWorldService - Unified orchestration for scenario validation pipeline.

Coordinates: generation -> validation -> save -> execution
with feedback loops, root trace IDs, and comprehensive instrumentation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from ..core.database import Database
from ..core.tracing import (
    generate_root_trace_id,
    reset_root_trace_id,
    set_root_trace_id,
    span,
)
from .scenario_factory import idea_to_yaml_dict, save_scenario_to_file
from .scenario_generator import (
    ScenarioIdea,
    generate_scenario_idea,
    regenerate_scenario_idea,
)
from .scenario_runner import ScenarioRunner, ScenarioRunResult
from .scenario_validator import (
    ValidationResult,
    get_rejection_feedback,
    validate_scenario_idea,
)
from .scoring import ScenarioScore

logger = logging.getLogger(__name__)


class ScenarioStatus(str, Enum):
    """Status of a scenario in the pipeline."""

    GENERATING = "generating"
    VALIDATING = "validating"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    SAVED = "saved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScenarioAttempt:
    """Tracks a single attempt at generating/validating a scenario."""

    attempt_number: int
    idea: ScenarioIdea | None = None
    validation: ValidationResult | None = None
    feedback: str | None = None
    trace_id: str | None = None


@dataclass
class ScenarioPipelineResult:
    """Complete result of running a scenario through the full pipeline."""

    # Identification
    root_trace_id: str
    scenario_name: str | None = None

    # Status
    status: ScenarioStatus = ScenarioStatus.GENERATING

    # Generation attempts
    attempts: list[ScenarioAttempt] = field(default_factory=list)
    total_attempts: int = 0

    # Final artifacts
    final_idea: ScenarioIdea | None = None
    final_validation: ValidationResult | None = None
    saved_path: Path | None = None

    # Execution results (if run)
    run_result: ScenarioRunResult | None = None
    score: ScenarioScore | None = None

    # Error tracking
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging/storage."""
        return {
            "root_trace_id": self.root_trace_id,
            "scenario_name": self.scenario_name,
            "status": self.status.value,
            "total_attempts": self.total_attempts,
            "saved_path": str(self.saved_path) if self.saved_path else None,
            "final_quality": (
                self.final_validation.quality_score if self.final_validation else None
            ),
            "run_success": self.run_result.success if self.run_result else None,
            "score": self.score.overall_score if self.score else None,
            "error": self.error,
        }


@dataclass
class SimWorldServiceConfig:
    """Configuration for SimWorldService."""

    # Retry settings
    max_retry_attempts: int = 3
    min_quality_score: float = 0.6

    # Output settings
    scenarios_dir: Path = field(default_factory=lambda: Path("scenarios"))
    save_rejected: bool = False  # Save rejected scenarios for analysis
    rejected_dir: Path = field(default_factory=lambda: Path("scenarios/rejected"))

    # Execution settings
    auto_run: bool = False  # Automatically run validated scenarios
    run_timeout: float = 60.0


class SimWorldService:
    """
    Unified orchestration service for the scenario validation pipeline.

    Responsibilities:
    1. Generate scenarios with LLM
    2. Validate with quality gate
    3. Regenerate with feedback on rejection (up to max_retry_attempts)
    4. Save validated scenarios
    5. Execute through ScenarioRunner
    6. Score results
    7. Track everything with root trace IDs
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Database | None = None,
        config: SimWorldServiceConfig | None = None,
    ):
        """Initialize the service.

        Args:
            llm: LangChain chat model for generation
            db: Database for player history (optional)
            config: Service configuration
        """
        self.llm = llm
        self.db = db
        self.config = config or SimWorldServiceConfig()

        # Ensure directories exist
        self.config.scenarios_dir.mkdir(parents=True, exist_ok=True)
        if self.config.save_rejected:
            self.config.rejected_dir.mkdir(parents=True, exist_ok=True)

        # Create runner
        self._runner = ScenarioRunner(llm=llm, db=db)

        logger.info(
            f"SimWorldService initialized (max_retries={self.config.max_retry_attempts}, "
            f"min_quality={self.config.min_quality_score})"
        )

    async def generate_validated_scenario(
        self,
        focus: str | None = None,
        difficulty: str | None = None,
    ) -> ScenarioPipelineResult:
        """Generate a scenario with feedback loop until validation passes.

        This is the core orchestration method that:
        1. Generates an initial scenario idea
        2. Validates it against quality gates
        3. If rejected, regenerates with feedback (up to max_retry_attempts)
        4. Returns the first passing scenario or the best failed attempt

        Args:
            focus: Optional focus area (e.g., "rescue_speed")
            difficulty: Optional difficulty level

        Returns:
            ScenarioPipelineResult with generation details
        """
        # Generate root trace ID for this entire pipeline
        root_trace_id = generate_root_trace_id()
        token = set_root_trace_id(root_trace_id)

        result = ScenarioPipelineResult(root_trace_id=root_trace_id)

        try:
            with span(
                "sim_world.generate_validated",
                focus=focus or "any",
                difficulty=difficulty or "any",
                max_attempts=self.config.max_retry_attempts,
            ):
                current_idea: ScenarioIdea | None = None

                for attempt_num in range(1, self.config.max_retry_attempts + 1):
                    result.total_attempts = attempt_num
                    attempt = ScenarioAttempt(
                        attempt_number=attempt_num,
                        trace_id=f"{root_trace_id}_{attempt_num}",
                    )

                    # === GENERATION ===
                    result.status = ScenarioStatus.GENERATING

                    with span(
                        f"scenario.generate.attempt_{attempt_num}",
                        attempt=attempt_num,
                        is_regeneration=attempt_num > 1,
                    ) as gen_span:
                        try:
                            if attempt_num == 1:
                                # First attempt: fresh generation
                                current_idea = await generate_scenario_idea(
                                    self.llm,
                                    focus=focus,
                                    difficulty=difficulty,
                                )
                            else:
                                # Subsequent attempts: regenerate with feedback
                                prev_attempt = result.attempts[-1]
                                current_idea = await regenerate_scenario_idea(
                                    self.llm,
                                    original_idea=prev_attempt.idea,
                                    rejection_feedback=prev_attempt.feedback or "",
                                    focus=focus,
                                    difficulty=difficulty,
                                )

                            attempt.idea = current_idea
                            gen_span.set_attribute("scenario_name", current_idea.name)
                            logger.info(
                                f"[SIM] Generated scenario: {current_idea.name} (attempt {attempt_num})"
                            )

                        except Exception as e:
                            logger.error(f"[SIM] Generation failed (attempt {attempt_num}): {e}")
                            gen_span.set_attribute("error", str(e))
                            result.attempts.append(attempt)
                            continue

                    # === VALIDATION ===
                    result.status = ScenarioStatus.VALIDATING

                    with span(
                        f"scenario.validate.attempt_{attempt_num}",
                        scenario_name=current_idea.name,
                    ) as val_span:
                        validation = validate_scenario_idea(current_idea)
                        attempt.validation = validation

                        val_span.set_attributes(
                            valid=validation.valid,
                            quality_score=validation.quality_score,
                            error_count=len(validation.errors),
                            warning_count=len(validation.warnings),
                        )

                        if (
                            validation.valid
                            and validation.quality_score >= self.config.min_quality_score
                        ):
                            # SUCCESS! Scenario passed validation
                            result.status = ScenarioStatus.ACCEPTED
                            result.final_idea = current_idea
                            result.final_validation = validation
                            result.scenario_name = current_idea.name
                            result.attempts.append(attempt)

                            logger.info(
                                f"[SIM] Scenario '{current_idea.name}' PASSED validation "
                                f"(attempt {attempt_num}, quality={validation.quality_score:.2f})"
                            )
                            break

                        else:
                            # REJECTED: Prepare feedback for next attempt
                            result.status = ScenarioStatus.REJECTED
                            attempt.feedback = get_rejection_feedback(
                                validation, self.config.min_quality_score
                            )
                            result.attempts.append(attempt)

                            logger.info(
                                f"[SIM] Scenario '{current_idea.name}' REJECTED "
                                f"(attempt {attempt_num}, quality={validation.quality_score:.2f})"
                            )
                            if validation.errors:
                                logger.debug(f"[SIM] Errors: {validation.errors}")
                            if validation.warnings:
                                logger.debug(f"[SIM] Warnings: {validation.warnings}")

                            if attempt_num < self.config.max_retry_attempts:
                                logger.info("[SIM] Will regenerate with feedback...")

                # Check if we succeeded
                if result.status != ScenarioStatus.ACCEPTED:
                    # All attempts failed - use the best one
                    best_attempt = max(
                        result.attempts,
                        key=lambda a: a.validation.quality_score if a.validation else 0,
                    )
                    result.final_idea = best_attempt.idea
                    result.final_validation = best_attempt.validation
                    result.scenario_name = (
                        best_attempt.idea.name if best_attempt.idea else None
                    )
                    result.error = (
                        f"Failed to pass validation after {result.total_attempts} attempts"
                    )

                    logger.warning(
                        f"[SIM] All {result.total_attempts} attempts failed. "
                        f"Best quality: {best_attempt.validation.quality_score if best_attempt.validation else 0:.2f}"
                    )

                return result

        finally:
            # Reset context
            reset_root_trace_id(token)

    async def save_scenario(
        self,
        result: ScenarioPipelineResult,
    ) -> ScenarioPipelineResult:
        """Save a validated scenario to disk.

        Args:
            result: Pipeline result with validated scenario

        Returns:
            Updated result with saved_path set
        """
        if not result.final_idea:
            result.error = "No scenario idea to save"
            result.status = ScenarioStatus.FAILED
            return result

        token = set_root_trace_id(result.root_trace_id)

        try:
            with span(
                "scenario.save",
                scenario_name=result.scenario_name,
                status=result.status.value,
            ) as save_span:
                # Determine output directory
                if result.status == ScenarioStatus.ACCEPTED:
                    output_dir = self.config.scenarios_dir
                elif self.config.save_rejected:
                    output_dir = self.config.rejected_dir
                else:
                    logger.info(
                        f"[SIM] Skipping save for rejected scenario: {result.scenario_name}"
                    )
                    return result

                # Convert to YAML and save
                scenario_dict = idea_to_yaml_dict(result.final_idea)

                # Add trace metadata
                scenario_dict["metadata"]["root_trace_id"] = result.root_trace_id
                scenario_dict["metadata"]["generation_attempts"] = result.total_attempts
                scenario_dict["metadata"]["final_quality_score"] = (
                    result.final_validation.quality_score
                    if result.final_validation
                    else 0
                )
                scenario_dict["metadata"]["generated_at"] = datetime.now().isoformat()

                saved_path = save_scenario_to_file(
                    scenario_dict,
                    output_dir,
                )

                result.saved_path = saved_path
                result.status = ScenarioStatus.SAVED

                save_span.set_attribute("saved_path", str(saved_path))

                logger.info(f"[SIM] Saved scenario to: {saved_path}")

                return result

        finally:
            reset_root_trace_id(token)

    async def run_scenario(
        self,
        result: ScenarioPipelineResult,
    ) -> ScenarioPipelineResult:
        """Execute a saved scenario through the runner.

        Args:
            result: Pipeline result with saved scenario

        Returns:
            Updated result with run_result and score
        """
        if not result.saved_path:
            result.error = "No saved scenario path to run"
            result.status = ScenarioStatus.FAILED
            return result

        token = set_root_trace_id(result.root_trace_id)

        try:
            result.status = ScenarioStatus.RUNNING

            with span(
                "scenario.run",
                scenario_name=result.scenario_name,
                scenario_path=str(result.saved_path),
            ) as run_span:
                run_result = await self._runner.run_scenario(
                    result.saved_path,
                    run_id=f"{result.root_trace_id[:8]}_run",
                )

                result.run_result = run_result

                run_span.set_attributes(
                    victory=run_result.victory,
                    deaths=run_result.deaths,
                    total_events=run_result.total_events,
                    interventions=run_result.eris_interventions,
                    success=run_result.success,
                )

                if run_result.success:
                    # Calculate score
                    result.score = run_result.calculate_score()
                    result.status = ScenarioStatus.COMPLETED

                    run_span.set_attribute("overall_score", result.score.overall_score)

                    logger.info(
                        f"[SIM] Scenario completed: victory={run_result.victory}, "
                        f"score={result.score.overall_score:.1f}"
                    )
                else:
                    result.status = ScenarioStatus.FAILED
                    result.error = run_result.error

                    logger.error(f"[SIM] Scenario run failed: {run_result.error}")

                return result

        finally:
            reset_root_trace_id(token)

    async def orchestrate(
        self,
        focus: str | None = None,
        difficulty: str | None = None,
        save: bool = True,
        run: bool | None = None,
    ) -> ScenarioPipelineResult:
        """Full pipeline: generate -> validate -> save -> run.

        This is the main entry point for end-to-end scenario validation.

        Args:
            focus: Optional focus area
            difficulty: Optional difficulty level
            save: Whether to save the scenario
            run: Whether to run the scenario (defaults to config.auto_run)

        Returns:
            Complete ScenarioPipelineResult
        """
        should_run = run if run is not None else self.config.auto_run

        # Step 1: Generate with feedback loop
        result = await self.generate_validated_scenario(
            focus=focus,
            difficulty=difficulty,
        )

        # Step 2: Save (if requested and scenario was accepted)
        if save and result.final_idea and result.status == ScenarioStatus.ACCEPTED:
            result = await self.save_scenario(result)

        # Step 3: Run (if requested and scenario was saved)
        if should_run and result.saved_path:
            result = await self.run_scenario(result)

        logger.info(
            f"[SIM] Orchestration complete: {result.scenario_name} "
            f"[status={result.status.value}, trace={result.root_trace_id}]"
        )

        return result

    async def orchestrate_batch(
        self,
        count: int = 10,
        focus: str | None = None,
        difficulty: str | None = None,
        save: bool = True,
        run: bool | None = None,
    ) -> list[ScenarioPipelineResult]:
        """Orchestrate multiple scenarios in sequence.

        Args:
            count: Number of scenarios to generate
            focus: Optional focus area
            difficulty: Optional difficulty level
            save: Whether to save scenarios
            run: Whether to run scenarios

        Returns:
            List of ScenarioPipelineResult objects
        """
        results = []

        with span(
            "sim_world.orchestrate_batch",
            count=count,
            focus=focus or "any",
            difficulty=difficulty or "any",
        ):
            for i in range(count):
                logger.info(f"[SIM] Orchestrating scenario {i + 1}/{count}")

                result = await self.orchestrate(
                    focus=focus,
                    difficulty=difficulty,
                    save=save,
                    run=run,
                )
                results.append(result)

        # Summary
        completed = sum(
            1 for r in results if r.status == ScenarioStatus.COMPLETED
        )
        accepted = sum(
            1
            for r in results
            if r.status
            in (
                ScenarioStatus.ACCEPTED,
                ScenarioStatus.SAVED,
                ScenarioStatus.COMPLETED,
            )
        )
        total_attempts = sum(r.total_attempts for r in results)
        avg_attempts = total_attempts / count if count > 0 else 0

        logger.info(
            f"[SIM] Batch complete: {accepted}/{count} accepted, "
            f"{completed}/{count} completed, "
            f"avg attempts: {avg_attempts:.1f}"
        )

        return results

    def get_trace_analysis(
        self,
        result: ScenarioPipelineResult,
    ) -> dict[str, Any]:
        """Get comprehensive trace analysis for a pipeline result.

        Returns data suitable for Logfire analysis.
        """
        analysis = {
            "root_trace_id": result.root_trace_id,
            "scenario_name": result.scenario_name,
            "status": result.status.value,
            "generation": {
                "total_attempts": result.total_attempts,
                "attempts": [
                    {
                        "attempt": a.attempt_number,
                        "trace_id": a.trace_id,
                        "name": a.idea.name if a.idea else None,
                        "quality": a.validation.quality_score if a.validation else None,
                        "valid": a.validation.valid if a.validation else None,
                        "errors": a.validation.errors if a.validation else [],
                        "warnings": a.validation.warnings if a.validation else [],
                    }
                    for a in result.attempts
                ],
            },
        }

        if result.run_result:
            analysis["execution"] = {
                "victory": result.run_result.victory,
                "deaths": result.run_result.deaths,
                "total_events": result.run_result.total_events,
                "tool_calls": result.run_result.total_tool_calls,
                "interventions": result.run_result.eris_interventions,
                "duration": result.run_result.duration_seconds,
            }

        if result.score:
            analysis["score"] = result.score.to_dict()

        return analysis
