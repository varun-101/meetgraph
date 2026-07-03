"""§5.2 cognee ontology — Pydantic DataPoint models passed to cognify(graph_model=).

Verified against cognee 1.2.2: custom graph models subclass
`cognee.low_level.DataPoint`; typed fields referencing other DataPoints become
edges; `metadata = {"index_fields": [...]}` controls embedding/indexing.
Shared Person/Project/Topic name strings are what let cognify merge entities
across meetings (doc header convention in pipeline.py).

Built lazily so `api` imports cleanly before `pip install cognee` completes.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def build_graph_model():
    """Return the root DataPoint model for cognify(graph_model=...)."""
    from typing import Optional

    from cognee.low_level import DataPoint

    class Person(DataPoint):
        name: str
        role: Optional[str] = None
        team: Optional[str] = None
        metadata: dict = {"index_fields": ["name"]}

    class Topic(DataPoint):
        name: str
        keywords: Optional[str] = None
        metadata: dict = {"index_fields": ["name"]}

    class ProjectNode(DataPoint):
        name: str
        status: Optional[str] = None
        metadata: dict = {"index_fields": ["name"]}

    class Decision(DataPoint):
        text: str
        confidence: Optional[str] = None
        date: Optional[str] = None
        made_by: Optional[Person] = None
        affects: Optional[ProjectNode] = None
        metadata: dict = {"index_fields": ["text"]}

    class ActionItemNode(DataPoint):
        text: str
        deadline: Optional[str] = None
        status: Optional[str] = None
        owner: Optional[Person] = None
        metadata: dict = {"index_fields": ["text"]}

    class MeetingNode(DataPoint):
        title: str
        date: Optional[str] = None
        project: Optional[ProjectNode] = None
        participants: list[Person] = []
        decisions: list[Decision] = []
        action_items: list[ActionItemNode] = []
        topics: list[Topic] = []
        metadata: dict = {"index_fields": ["title"]}

    return MeetingNode
