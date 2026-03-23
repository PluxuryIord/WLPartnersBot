from .base import Base
from .admin import Admin
from .admin_notification import AdminNotification
from .alert import Alert
from .settings import Settings
from .text import Texts
from .topic_messages import TopicMessages
from .forward_topic_messages import ForwardTopicMessages
from .user import User
from .support import Support

from .winners import Winner
from .qr_code import QRCode
from .randomizer import Randomizer
from .user_auth import UserAuth
from .group_chat import GroupChat
from .event_question import EventQuestion
from .event_answer import EventAnswer

Base.create_tables()
Settings.startup()
