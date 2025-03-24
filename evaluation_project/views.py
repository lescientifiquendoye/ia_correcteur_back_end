from django.http import HttpResponseForbidden, FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
import os
from django.conf import settings

class UploadFileView(APIView):
    """
    Vue pour servir les fichiers du répertoire 'uploads' aux utilisateurs connectés.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, file_path):
        """
        Méthode pour servir un fichier aux utilisateurs connectés.
        """
        # Chemin complet du fichier
        full_path = os.path.join(settings.MEDIA_ROOT, file_path)

        # Vérifiez que le fichier existe
        if not os.path.exists(full_path):
            return Response(
                {"detail": "Fichier non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Vérifiez que le chemin est sécurisé (évite les attaques par traversal)
        if not os.path.abspath(full_path).startswith(os.path.abspath(settings.MEDIA_ROOT)):
            return Response(
                {"detail": "Accès non autorisé."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Serve the file
        try:
            return FileResponse(open(full_path, 'rb'))
        except Exception as e:
            return Response(
                {"detail": f"Erreur lors de la lecture du fichier : {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )