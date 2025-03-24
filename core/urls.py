from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView, LoginView, LogoutView,
    RegisteredEmailViewSet, ClasseViewSet, ProfesseurViewSet, EtudiantViewSet,
    MatiereViewSet, EvaluationViewSet, ReponseEleveViewSet
)

router = DefaultRouter()
router.register(r'registered-emails', RegisteredEmailViewSet)
router.register(r'classes', ClasseViewSet)
router.register(r'professeurs', ProfesseurViewSet)
router.register(r'etudiants', EtudiantViewSet)
router.register(r'matieres', MatiereViewSet, basename='matiere')
router.register(r'evaluations', EvaluationViewSet, basename='evaluation')
router.register(r'reponses', ReponseEleveViewSet, basename='reponse')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    # JWT specific URLs
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]