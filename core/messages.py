"""
Messages exchanged between agents (inspired by FIPA ACL).

A message is a communicative act (speech act): it carries a performative type,
a sender, a receiver and a payload. The performative set covers the "Path A"
scenarios: a tender (Contract Net) and a data dispute by the validator.

Sources: the FIPA ACL specifications and the FIPA Contract Net Interaction
Protocol; Wooldridge, An Introduction to MultiAgent Systems.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class Performative(str, Enum):
    REQUEST = "request"               # ask to perform a task
    INFORM = "inform"                 # report a fact / result
    REPORT = "report"                 # report subtask completion
    CONFIRM = "confirm"               # confirm completion
    # Contract Net (tender for an executor)
    CFP = "cfp"                       # call for proposals — announce a subtask
    PROPOSE = "propose"               # a candidate's bid
    ACCEPT_PROPOSAL = "accept"        # bid accepted (candidate becomes primary)
    REJECT_PROPOSAL = "reject"        # bid rejected (candidate becomes a backup)
    # quality control
    CHALLENGE = "challenge"           # the validator disputes the data


@dataclass
class AgentMessage:
    performative: Performative
    sender: str
    receiver: str
    content: Any = None
    conversation_id: Optional[int] = None  # usually = task_id

    def __repr__(self) -> str:
        return (f"<{self.performative.value} {self.sender} -> {self.receiver} "
                f"conv={self.conversation_id}>")
