from .models import User


class PersonaAuthMiddleware:
    """
    Middleware that inspects the 'X-Active-User-Id' header or session,
    allowing instant 1-click persona switching from the React frontend.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.headers.get('X-Active-User-Id') or request.GET.get('active_user_id')
        if user_id:
            try:
                user = User.objects.get(pk=user_id, is_active=True)
                request.user = user
            except (User.DoesNotExist, ValueError):
                pass
        return self.get_response(request)
