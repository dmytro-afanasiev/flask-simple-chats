"""Initialization of actually the main chats blueprint."""
from flask import Blueprint

chats = Blueprint('chats', __name__, url_prefix='/chats')

from . import events
from .models import Message
from .views import UserChatsList, UserChatBegin, UsersChatGoing

chats.add_url_rule('/list', view_func=UserChatsList.as_view('list'))
chats.add_url_rule('/begin/<string:companion_username>', view_func=UserChatBegin.as_view('begin'))
chats.add_url_rule('/going', view_func=UsersChatGoing.as_view('going'))
