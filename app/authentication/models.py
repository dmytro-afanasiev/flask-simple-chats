"""Main models to realize an authentication. Chats table is also specified here in order to prevent from circular
import with app/chats/models.py"""
import datetime
from functools import lru_cache

from flask import current_app
from itsdangerous import TimedJSONWebSignatureSerializer
from sqlalchemy import and_, exists
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.authentication.email import send_mail
from app.authentication.exceptions import UserNotFoundByIndexError
from app.chats.exceptions import ChatNotFoundByIndexesError, ChatAlreadyExistsError
from . import logger

chats = db.Table('chats',
                 db.Column('chat_id', db.Integer, primary_key=True),
                 db.Column('user1_id', db.Integer, db.ForeignKey('users.user_id'), nullable=False),
                 db.Column('user2_id', db.Integer, db.ForeignKey('users.user_id'), nullable=False))


class User(db.Model):
    """
    Main user model with enabled password hashing and verifying
    """
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    date_joined = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @property
    def password(self):
        logger.warning("Someone tried to read user's password")
        raise AttributeError('Password cannot be read')

    def set_password(self, password: str):
        """Hashes user password using werkzeug method and saves it into the appropriate attribute"""
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password: str) -> bool:
        """Makes hash from given password and compares it with already existing one. Uses werkzeug method."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'User - {self.username}'

    @classmethod
    def get_user_by_id(cls, user_id: int) -> 'User':
        """Return user with given id if exists, else - raise error"""
        user = cls.query.get(user_id)
        if not user:
            logger.info('User was not found by index')
            raise UserNotFoundByIndexError
        return user

    def send_email(self, subject: str, text: str):
        """Sends an e-mail with given subject and text to the current user"""
        send_mail(self.email, subject, text)

    def get_reset_password_token(self, expiration_period: int = None) -> str:
        """Generate web token with given expiration period and saves the current user's id in.
        Web signature is based on application secret key, so it must be saved from others.
        :param expiration_period: time in seconds which must go by before the token revocation.
        :type expiration_period: int
        :returns generated token
        :rtype str
        """
        if not expiration_period:
            expiration_period = current_app.config['PASSWORD_DEFAULT_EXPIRES_IN']
        secret_key = current_app.config['SECRET_KEY']
        serializer = TimedJSONWebSignatureSerializer(secret_key, expiration_period)
        token = serializer.dumps({'user_id': self.user_id}).decode()
        return token

    @classmethod
    def get_user_by_reset_password_token(cls, token: str) -> 'User':
        """Deserializes token with current app secret key and receives saved user's id.
        Function return a user with such an id
        :param token: Token received from password reset view
        :type token: str
        :returns: user with received id
        :rtype User
        """
        serializer = TimedJSONWebSignatureSerializer(current_app.config['SECRET_KEY'])
        user_id = serializer.loads(token)['user_id']
        return cls.get_user_by_id(user_id)

    @staticmethod
    def create_chat(user1_id: int, user2_id: int):
        """Crete a note in chats table which connects two user in chat.
        Params can be given in an arbitrary order, so only ascending sequence of users ids will be saved to DB.
        If a chats between given users already exists, error will be thrown.
        db.session must be committed after executing the function to save changes.
        :param user1_id: first user's id to check
        :param user2_id: second user's id to check"""
        user1_id, user2_id = sorted([user1_id, user2_id])
        if not User.is_chat_between(user1_id, user2_id):
            db.session.execute(chats.insert(
                values=[{'user1_id': user1_id, 'user2_id': user2_id}, ]))
            User.is_chat_between.cache_clear()
        else:
            logger.info("Chat already exists when create_chat method is executed")
            raise ChatAlreadyExistsError

    @staticmethod
    def delete_chat(two_users_ids: list = None, chat_id: int = None):
        """Delete a chat between given users from db. Ids can be put in an arbitrary order like in a function above,
        but in a list, by the first argument. Instead of users ids, chat id can be put directly.
        If the chat does not exist, an error will be thrown. db.session must be committed after executing
        the function to save changes.
        :param two_users_ids: users ids in a list. The chat between them will be deleted
        :type two_users_ids: list
        :param chat_id: the chat, which will be deleted
        :type chat_id: int
        """
        chat_id = chat_id or User.get_chat_id_by_users_ids(*two_users_ids)
        db.session.execute(chats.delete().where(chats.c.chat_id == chat_id))
        User.is_chat_between.cache_clear()
        User.get_chat_id_by_users_ids.cache_clear()

    @staticmethod
    @lru_cache(maxsize=256)
    def is_chat_between(user1_id: int, user2_id: int) -> bool:
        """Check if two users have chat together.
        :param user1_id: first user's id to check
        :param user2_id: second user's id to check
        :returns boolean value: if it is true, users have already had chat together.
        If it is false - they have not had"""
        user1_id, user2_id = sorted([user1_id, user2_id])
        return db.session.query(
            exists(chats).where(and_(chats.c.user1_id == user1_id, chats.c.user2_id == user2_id))).scalar()

    @staticmethod
    @lru_cache(maxsize=256)
    def get_chat_id_by_users_ids(user1_id: int, user2_id: int) -> int:
        """
        Return a unique chat's id which connects two users from given ids. If a chat does not exist, raises error.
        :param user1_id: first user's id.
        :type user1_id: int
        :param user2_id: second user's id.
        :type user2_id:int
        :return: chat id
        :rtype:int
        """
        user1_id, user2_id = sorted([user1_id, user2_id])
        chat_id = db.session.query(chats.c.chat_id).filter(
            and_(chats.c.user1_id == user1_id, chats.c.user2_id == user2_id)).scalar()
        if not chat_id:
            logger.warning('Chat must be found by index, but it is not')
            raise ChatNotFoundByIndexesError
        return chat_id

    def get_authentication_token(self, expires_in: int = None) -> str:
        """
        Generates authentication token for the current user so that he can access the secure functionality without
        putting login and password every request.
        :param expires_in: time in seconds which must go by before the token is spoilt. If nothing is put, a default
        value will be chosen.
        :type expires_in: int
        :return: generated token
        :rtype: str
        """
        if not expires_in:
            expires_in = current_app.config['AUTHENTICATION_TOKEN_DEFAULT_EXPIRES_IN']
        serializer = TimedJSONWebSignatureSerializer(current_app.config['SECRET_KEY'], expires_in)
        return serializer.dumps({'user_id': self.user_id}).decode()

    @staticmethod
    def get_user_by_authentication_token(token: str) -> 'User':
        """
        Deserializes the token and returns a user who matches the received id. Raises BadSignature or SignatureExpired
        errors if necessary. After that a user who are trying to access must be refused.
        :param token: token string received from a client.
        :type token: str
        :return: User instance
        :rtype: User
        """
        serializer = TimedJSONWebSignatureSerializer(current_app.config['SECRET_KEY'])
        user_id = serializer.loads(token)['user_id']
        return User.get_user_by_id(user_id)
