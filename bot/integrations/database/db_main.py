"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from dataclasses import dataclass

from .models.main_base import User, Admin, Alert, AdminNotification, Randomizer
from .models.main_base import TopicMessages, ForwardTopicMessages, Settings, Texts, Support, Winner, QRCode
from .models.main_base import UserAuth
from sqlalchemy import or_, and_, not_, null


@dataclass()
class DB:
    User = User
    Admin = Admin
    Settings = Settings
    Alert = Alert
    Text = Texts
    AdminNotification = AdminNotification
    TopicMessages = TopicMessages
    ForwardTopicMessages = ForwardTopicMessages
    Support = Support
    Winner = Winner
    QRCode = QRCode
    Randomizer = Randomizer
    UserAuth = UserAuth

    sql_or = or_
    sql_and = and_
    sql_not = not_
    sql_null = null
