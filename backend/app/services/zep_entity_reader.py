from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EntityNode:
    uuid: str
    name: str
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityNode":
        return cls(
            uuid=str(data.get("uuid") or data.get("id") or data.get("name") or ""),
            name=str(data.get("name") or data.get("title") or "Unnamed"),
            labels=list(data.get("labels") or []),
            summary=str(data.get("summary") or data.get("description") or ""),
            attributes=dict(data.get("attributes") or data.get("properties") or {}),
            related_edges=list(data.get("related_edges") or []),
            related_nodes=list(data.get("related_nodes") or []),
        )

    def get_entity_type(self) -> str:
        if self.labels:
            return str(self.labels[0])
        return str(self.attributes.get("entity_type") or self.attributes.get("type") or "Entity")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }


@dataclass
class FilteredEntities:
    entities: List[EntityNode] = field(default_factory=list)
    entity_types: set = field(default_factory=set)
    total_count: int = 0
    filtered_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [item.to_dict() for item in self.entities],
            "entity_types": sorted(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    def filter_defined_entities(self, graph_id: str, defined_entity_types=None, enrich_with_edges: bool = True) -> FilteredEntities:
        return FilteredEntities()

    def get_entity_with_context(self, graph_id: str, entity_uuid: str):
        return None

    def get_entities_by_type(self, graph_id: str, entity_type: str, enrich_with_edges: bool = True) -> List[EntityNode]:
        return []
