from typing import Dict

from flask_login import UserMixin


class User(UserMixin):
    cache: Dict[str, 'User'] = {}

    def __init__(self, id_, name, email, profile_pic):
        self.profile_pic = profile_pic
        self.email = email
        self.name = name
        self.id = id_

    @staticmethod
    def create(id_, name, email, picture) -> 'User':
        user = User(id_, name, email, picture)
        User.cache[id_] = user
        return user

    @staticmethod
    def get(id_: str) -> 'User':
        return User.cache.get(id_)

    def __str__(self) -> str:
        return f"{self.name}:{self.email}:{self.id}"


