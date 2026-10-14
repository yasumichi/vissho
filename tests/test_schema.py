"""Tests for dynamic schema generation."""

from pydantic import ValidationError
import pytest

from vissho.config import ColumnDefinition
from vissho.core.schema import (
    create_curriculum_plan_model,
    create_instruction_row_model,
    get_json_schema,
)


def test_create_instruction_row_model_basic() -> None:
    """Test dynamic row model generation with basic columns."""
    columns = [
        ColumnDefinition(name="topic", description="Unit Topic"),
        ColumnDefinition(name="learning_objectives", description="Objectives"),
        ColumnDefinition(name="allocated_minutes", description="Allocated time"),
        ColumnDefinition(name="source_slides", description="Source slides"),
    ]

    RowModel = create_instruction_row_model(columns)

    # Valid instance
    instance = RowModel(
        topic="Introduction to Python",
        learning_objectives="Understand variables",
        allocated_minutes=30,
        source_slides=[1, 2, 3],
    )

    assert instance.topic == "Introduction to Python"
    assert instance.allocated_minutes == 30
    assert instance.source_slides == [1, 2, 3]


def test_auto_inject_required_internal_fields() -> None:
    """Ensure allocated_minutes and source_slide_numbers are injected if omitted by user."""
    columns = [
        ColumnDefinition(name="activity", description="Learning activity"),
    ]

    RowModel = create_instruction_row_model(columns)

    # Note that source_slide_numbers has default factory, allocated_minutes defaults to 0 or requires int
    instance = RowModel(
        activity="Group Discussion",
        allocated_minutes=15,
    )

    assert instance.activity == "Group Discussion"
    assert instance.allocated_minutes == 15
    assert instance.source_slide_numbers == []


def test_create_curriculum_plan_model_and_json_schema() -> None:
    """Test building complete curriculum plan model and generating JSON schema for Ollama."""
    columns = [
        ColumnDefinition(name="session_number", description="Session number"),
        ColumnDefinition(name="topic", description="Topic"),
        ColumnDefinition(name="activities", description="Activities"),
        ColumnDefinition(name="allocated_minutes", description="Minutes"),
        ColumnDefinition(name="source_slides", description="Slide IDs"),
    ]

    CurriculumModel = create_curriculum_plan_model(columns)

    schema = get_json_schema(CurriculumModel)
    assert schema["type"] == "object"
    assert "sessions" in schema["properties"]
    assert "unassigned_slides" in schema["properties"]

    # Test validating sample curriculum data
    curriculum = CurriculumModel(
        sessions=[
            {
                "session_number": 1,
                "session_title": "Basics",
                "rows": [
                    {
                        "session_number": "第1回",
                        "topic": "Overview",
                        "activities": "Lecture and Q&A",
                        "allocated_minutes": 90,
                        "source_slides": [1, 2, 3, 4],
                    }
                ],
                "total_minutes": 90,
            }
        ],
        unassigned_slides=[5],
    )

    assert len(curriculum.sessions) == 1
    assert curriculum.sessions[0].total_minutes == 90
    assert curriculum.sessions[0].rows[0].allocated_minutes == 90
    assert curriculum.unassigned_slides == [5]
