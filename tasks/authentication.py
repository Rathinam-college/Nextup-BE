from rest_framework import authentication
from rest_framework import exceptions
from .models import User


class HeaderOrSessionAuthentication(authentication.BaseAuthentication):
    """
    Custom DRF Authentication:
    Allows authenticating via X-Active-User-Id header or Django session user.
    """
    def authenticate(self, request):
        user_id = (
            request.headers.get('X-Active-User-Id')
            or request.headers.get('x-active-user-id')
            or getattr(request, 'META', {}).get('HTTP_X_ACTIVE_USER_ID')
            or request.query_params.get('active_user_id')
        )
        if user_id:
            try:
                user = User.objects.get(pk=user_id, is_active=True)
                return (user, None)
            except (User.DoesNotExist, ValueError):
                # If the persona ID is stale or invalid, safely ignore it instead of blocking auth
                pass

        # Check underlying Django request session
        django_req = getattr(request, '_request', request)
        if hasattr(django_req, 'user') and django_req.user.is_authenticated:
            return (django_req.user, None)

        return None
