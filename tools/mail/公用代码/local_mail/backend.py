"""Local mail service over a persisted mailbox environment."""
from .automation import AutomationMixin
from .compose import ComposeMixin
from .core import MailCore
from .directory import DirectoryMixin
from .messages import MessagesMixin


class MailStore(MessagesMixin, DirectoryMixin, ComposeMixin, AutomationMixin, MailCore):
    """Mail operations share one atomic store and one authorization model."""
