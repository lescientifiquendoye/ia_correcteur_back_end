from django.utils.deprecation import MiddlewareMixin

class DisableCSRFForAPI(MiddlewareMixin):
    """
    Middleware personnalisé pour désactiver la protection CSRF pour les routes API.
    """
    def process_request(self, request):
        if request.path.startswith('/api/'):  # Ignorer CSRF pour les routes /api/
            setattr(request, '_dont_enforce_csrf_checks', False)