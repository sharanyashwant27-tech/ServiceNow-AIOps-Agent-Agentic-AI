from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Engineer:
    name: str
    email: str
    skills: list[str]
    id: str = field(default_factory=lambda: str(uuid4()))
    assignment_group: str = "IT Support"
    max_workload: int = 8
    current_workload: int = 0
    active: bool = True

    @property
    def capacity_score(self) -> float:
        if self.max_workload <= 0:
            return 0.0
        return max(0.0, 1.0 - (self.current_workload / self.max_workload))
