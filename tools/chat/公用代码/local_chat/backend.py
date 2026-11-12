"""WeChat-style conversations with per-user relationships and content copies."""
from .contacts import ContactsMixin
from .conversations import ConversationsMixin
from .core import ChatCore
from .messages import MessagesMixin
from .personal import PersonalMixin


class ChatStore(ContactsMixin, ConversationsMixin, MessagesMixin, PersonalMixin, ChatCore):
    """Public chat operations share one atomic store and a fixed permission model."""
