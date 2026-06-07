from dataclasses import dataclass
from typing import Optional


@dataclass
class Task:
    id: Optional[int] = None

    month: str = ""

    geo_list: str = ""

    deadline: str = ""

    status: str = "created"