from typing import List, Optional

from pydantic import BaseModel


class Node(BaseModel):
    name: str
    children: List["Node"] = []
    parent_name: Optional[str] = None

    def size(self) -> int:
        return 1 + sum(c.size() for c in self.children)


Node.update_forward_refs()
