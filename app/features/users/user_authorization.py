from app.features.users.user_exceptions import InsufficientPrivilegesError
from app.shared.enums import UserRole


class UserAuthorizationPolicy:
    @staticmethod
    def validate(actor, target=None, requested_role=None):
        if actor is None or actor.is_active is False or actor.role not in (UserRole.MANAGER, UserRole.MAINTAINER):
            raise InsufficientPrivilegesError('Privilégios insuficientes para administrar usuários.')
        protected_target = target is not None and target.role == UserRole.MAINTAINER
        if actor.role != UserRole.MAINTAINER and (protected_target or requested_role == UserRole.MAINTAINER):
            raise InsufficientPrivilegesError('Somente mantenedores podem administrar o papel de mantenedor.')
