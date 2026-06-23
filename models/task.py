from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Task:
    """A budget-collection task as stated by the analyst."""
    id: Optional[int] = None
    month: str = ""
    geo_list: List[str] = field(default_factory=list)
    # Optional channel filter. Empty -> collect all channels of each GEO;
    # non-empty -> collect only these channels (where they exist for the GEO).
    channels: List[str] = field(default_factory=list)
    deadline: str = ""
    status: str = "created"
