"""
Message bus — a minimal internal "mailbox" between agents.

Each agent registers under its own name. To send a message, an agent calls
await bus.send(msg); the bus delivers it to the recipient's receive() method.
This gives an explicit communication protocol between autonomous components —
a defining feature of a multi-agent system.
"""

import logging
from typing import Dict

from core.messages import AgentMessage

logger = logging.getLogger(__name__)


class MessageBus:
    def __init__(self):
        self._agents: Dict[str, "object"] = {}

    def register(self, name: str, agent) -> None:
        """Add an agent to the bus address book."""
        self._agents[name] = agent
        logger.info("Bus: registered agent '%s'", name)

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._agents

    def get(self, name: str):
        return self._agents.get(name)

    async def send(self, message: AgentMessage) -> None:
        """Deliver a message to its recipient (asynchronously)."""
        logger.info("Bus: %s", message)
        agent = self._agents.get(message.receiver)
        if agent is None:
            logger.warning("Bus: recipient '%s' not found", message.receiver)
            return
        await agent.receive(message)
