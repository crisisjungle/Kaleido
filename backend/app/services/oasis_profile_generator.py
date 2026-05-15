from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class OasisProfile:
    agent_id: int
    name: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id, "name": self.name, "description": self.description}

    def to_reddit_format(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id, "username": self.name, "bio": self.description}

    def to_twitter_format(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id, "username": self.name, "description": self.description}


class OasisProfileGenerator:
    def generate_profiles_from_entities(self, entities: List[Any], use_llm: bool = True) -> List[OasisProfile]:
        return [
            OasisProfile(
                agent_id=index + 1,
                name=getattr(entity, "name", None) or f"agent_{index + 1}",
                description=getattr(entity, "summary", "") or "",
            )
            for index, entity in enumerate(entities or [])
        ]
