"""
Base agent class.

An agent is an autonomous entity with its own name, access to the bus (to talk
to other agents) and a notify channel (to message the human in Telegram).
Subclasses override receive() — the reaction to incoming messages from peers.

The notion of an agent (autonomy, reactivity, pro-activeness, social ability)
follows Wooldridge & Jennings, "Intelligent Agents: Theory and Practice".
"""

import logging
from typing import Awaitable, Callable, Optional

from core.bus import MessageBus
from core.messages import AgentMessage

logger = logging.getLogger(__name__)

# Human-notification channel type: notify(chat_id, text, keyboard=None)
NotifyFn = Callable[..., Awaitable[None]]


class BaseAgent:
    def __init__(self, name: str, bus: MessageBus, notify: Optional[NotifyFn] = None):
        self.name = name
        self.bus = bus
        self._notify = notify
        self.bus.register(name, self)

    async def notify_user(self, chat_id: int, text: str, keyboard=None) -> None:
        """Message the human (if a channel is set)."""
        if self._notify is not None:
            await self._notify(chat_id, text, keyboard)

    async def send(self, message: AgentMessage) -> None:
        """Message another agent through the bus."""
        await self.bus.send(message)

    async def receive(self, message: AgentMessage) -> None:
        """React to an incoming message. Overridden in subclasses."""
        logger.debug("%s received %s but does not handle it", self.name, message)
