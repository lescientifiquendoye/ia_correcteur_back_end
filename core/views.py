from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import transaction
from rest_framework import viewsets, status, generics
from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.timezone import now   
import re
import logging
from datetime import datetime, timedelta
import jwt
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

from .models import (
    RegisteredEmail, Classe, Professeur, Etudiant, Matiere, 
    Evaluation, Question, ReponseEleve, ReponseQuestion
)
from .serializers import (
    UserSerializer, RegisteredEmailSerializer, RegisterSerializer,
    LoginSerializer, ClasseSerializer, ProfesseurSerializer, 
    EtudiantSerializer, MatiereSerializer, EvaluationSerializer,
    QuestionSerializer, ReponseEleveSerializer, ReponseQuestionSerializer
)
from .permissions import IsAdmin, IsProfesseur, IsEtudiant, IsProfesseurOrAdmin
from .utils import extract_text, ask_deepseek, evaluate_student_answer


User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]
    
    @transaction.atomic
    def post(self, request):
        # Valider les données de la requête
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        try:
            # Vérifier si l'email est enregistré et non utilisé
            registered_email = RegisteredEmail.objects.get(email=data['email'], is_registered=False)
        except RegisteredEmail.DoesNotExist:
            return Response({"error": "Email non autorisé ou déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Créer l'utilisateur
            user = User.objects.create_user(
                email=data['email'],
                password=data['password'],
                role=registered_email.role
            )
            
            # Créer un Professeur ou un Étudiant en fonction du rôle
            if registered_email.role == 'PROFESSEUR':
                Professeur.objects.create(
                    user=user,
                    nom=data['nom'],
                    prenom=data['prenom']
                )
            elif registered_email.role == 'ETUDIANT':
                #if not data.get('classe_id'):
                    #return Response({"error": "Classe requise pour un étudiant"}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    classe = Classe.objects.get(id=registered_email.classe.id)
                    Etudiant.objects.create(
                        user=user,
                        classe=classe,
                        nom=data['nom'],
                        prenom=data['prenom']
                    )
                except Classe.DoesNotExist:
                    return Response({"error": "Classe non trouvée"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Marquer l'email comme enregistré
            registered_email.is_registered = True
            registered_email.save()
            
            # Générer un JWT pour l'utilisateur
            refresh = RefreshToken.for_user(user)
            tokens = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            
            # Retourner la réponse avec les tokens JWT et les données de l'utilisateur
            return Response({
                "tokens": tokens,
                "user": UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            # En cas d'erreur, annuler la transaction et retourner une erreur
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password']
        )
        
        if not user:
            return Response({"error": "Identifiants invalides"}, status=status.HTTP_401_UNAUTHORIZED)
        
        login(request, user)
        
        # Générer un JWT pour l'utilisateur
        refresh = RefreshToken.for_user(user)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        
        user_data = UserSerializer(user).data
        
        # Ajouter des informations supplémentaires selon le rôle
        if user.role == 'PROFESSEUR':
            try:
                professeur = Professeur.objects.get(user=user)
                user_data['profile'] = ProfesseurSerializer(professeur).data
            except Professeur.DoesNotExist:
                pass
        elif user.role == 'ETUDIANT':
            try:
                etudiant = Etudiant.objects.get(user=user)
                user_data['profile'] = EtudiantSerializer(etudiant).data
            except Etudiant.DoesNotExist:
                pass
        
        return Response({
            "tokens": tokens,
            "user": user_data
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response({"error": "Refresh token requis"}, status=status.HTTP_400_BAD_REQUEST)
                
            token = RefreshToken(refresh_token)
            token.blacklist()  # Blacklist the token to prevent reuse
            
            logout(request)
            return Response({"success": "Déconnexion réussie"}, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"error": "Token invalide ou expiré"}, status=status.HTTP_400_BAD_REQUEST)


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({"error": "Refresh token requis"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            refresh = RefreshToken(refresh_token)
            tokens = {
                'access': str(refresh.access_token),
            }
            
            return Response(tokens, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"error": "Token invalide ou expiré"}, status=status.HTTP_401_UNAUTHORIZED)


# Le reste des ViewSets reste le même, mais nous devons ajouter JWTAuthentication
class RegisteredEmailViewSet(viewsets.ModelViewSet):
    queryset = RegisteredEmail.objects.all()
    serializer_class = RegisteredEmailSerializer
    permission_classes = [IsAdmin]
    authentication_classes = [JWTAuthentication]


class ClasseViewSet(viewsets.ModelViewSet):
    queryset = Classe.objects.all()
    serializer_class = ClasseSerializer
    permission_classes = [IsProfesseurOrAdmin]
    authentication_classes = [JWTAuthentication]


class ProfesseurViewSet(viewsets.ModelViewSet):
    queryset = Professeur.objects.all()
    serializer_class = ProfesseurSerializer
    permission_classes = [IsAdmin]
    authentication_classes = [JWTAuthentication]


class EtudiantViewSet(viewsets.ModelViewSet):
    queryset = Etudiant.objects.all()
    serializer_class = EtudiantSerializer
    permission_classes = [IsProfesseurOrAdmin]
    authentication_classes = [JWTAuthentication]


class MatiereViewSet(viewsets.ModelViewSet):
    serializer_class = MatiereSerializer
    permission_classes = [IsProfesseurOrAdmin]
    authentication_classes = [JWTAuthentication]
    
    def get_queryset(self):
        if self.request.user.role == 'ADMIN':
            return Matiere.objects.all()
        elif self.request.user.role == 'PROFESSEUR':
            try:
                professeur = Professeur.objects.get(user=self.request.user)
                return Matiere.objects.filter(professeur=professeur)
            except Professeur.DoesNotExist:
                return Matiere.objects.none()
        return Matiere.objects.none()
    
    def perform_create(self, serializer):
        professeur = Professeur.objects.get(user=self.request.user)
        serializer.save(professeur=professeur)


class EvaluationViewSet(viewsets.ModelViewSet):
    serializer_class = EvaluationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'ADMIN':
            return Evaluation.objects.all()
        elif user.role == 'PROFESSEUR':
            try:
                professeur = Professeur.objects.get(user=user)
                return Evaluation.objects.filter(matiere__professeur=professeur)
            except Professeur.DoesNotExist:
                return Evaluation.objects.none()
        elif user.role == 'ETUDIANT':
            try:
                etudiant = Etudiant.objects.get(user=user)
                return Evaluation.objects.filter(matiere__classe=etudiant.classe)
            except Etudiant.DoesNotExist:
                return Evaluation.objects.none()
        
        return Evaluation.objects.none()
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        try:
            if request.user.role != 'PROFESSEUR':
                return Response({"error": "Seuls les professeurs peuvent créer des évaluations"}, 
                               status=status.HTTP_403_FORBIDDEN)
            
            professeur = Professeur.objects.get(user=request.user)
            matiere_id = request.data.get('matiere_id')
            
            try:
                matiere = Matiere.objects.get(id=matiere_id, professeur=professeur)
            except Matiere.DoesNotExist:
                return Response({"error": "Matière non trouvée ou non autorisée"}, 
                               status=status.HTTP_400_BAD_REQUEST)
            
            fichier = request.FILES.get('fichier')
            format_fichier = request.data.get('format')
            titre = request.data.get('titre')
            date_evaluation_str = request.data.get('date_evaluation')
            date_evaluation = parse_datetime(date_evaluation_str) if date_evaluation_str else now()

            if not fichier or format_fichier not in ['pdf', 'text', 'latex']:
                return Response({"error": "Format de fichier non supporté"}, 
                               status=status.HTTP_400_BAD_REQUEST)
            
            file_path = default_storage.save(f"evaluations/{now().strftime('%Y%m%d_%H%M%S')}_{fichier.name}", fichier)
            
            contenu = extract_text(default_storage.path(file_path), format_fichier)
            questions_text = re.findall(r"(\d+[\)\.-]\s?.*?)(?=(\d+[\)\.-]|$))", contenu, re.S)
            
            evaluation = Evaluation.objects.create(
                matiere=matiere,
                titre=titre,
                fichier=file_path,
                format=format_fichier,
                date_evaluation=date_evaluation,
                sujet=contenu
            )
            
            total_points = 0
            
            for match in questions_text:
                question_text = match[0].strip()
                points = re.search(r"\((\d+)\s?pts?\)", question_text, re.I)
                bareme = int(points.group(1)) if points else 1
                reponse = ask_deepseek(question_text)
                
                Question.objects.create(
                    evaluation=evaluation,
                    contenu=question_text,
                    bareme=bareme,
                    reponse_ia=reponse
                )
                
                total_points += bareme
            
            evaluation.bareme_total = total_points
            evaluation.save()
            
            return Response(EvaluationSerializer(evaluation).data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'évaluation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        try:
            evaluation = self.get_object()
            
            # Vérifiez les permissions
            if request.user.role == 'PROFESSEUR':
                professeur = Professeur.objects.get(user=request.user)
                if evaluation.matiere.professeur != professeur:
                    return Response({"error": "Vous n'êtes pas autorisé à modifier cette évaluation"},
                                status=status.HTTP_403_FORBIDDEN)
            elif request.user.role != 'ADMIN':
                return Response({"error": "Seuls les professeurs et administrateurs peuvent modifier des évaluations"},
                            status=status.HTTP_403_FORBIDDEN)
            
            # Mise à jour des champs de base de l'évaluation
            serializer = self.get_serializer(evaluation, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            
            # Mise à jour des questions si fournies
            questions_data = request.data.get('questions', [])
            if questions_data:
                for question_data in questions_data:
                    question_id = question_data.get('id')
                    if question_id:
                        # Mise à jour d'une question existante
                        try:
                            question = Question.objects.get(id=question_id, evaluation=evaluation)
                            
                            # Mise à jour des champs de la question
                            if 'contenu' in question_data:
                                question.contenu = question_data['contenu']
                            if 'bareme' in question_data:
                                question.bareme = question_data['bareme']
                            if 'reponse_ia' in question_data:
                                question.reponse_ia = question_data['reponse_ia']
                            
                            question.save()
                        except Question.DoesNotExist:
                            return Response({"error": f"Question avec ID {question_id} non trouvée"},
                                        status=status.HTTP_400_BAD_REQUEST)
                    else:
                        # Création d'une nouvelle question
                        Question.objects.create(
                            evaluation=evaluation,
                            contenu=question_data.get('contenu', ''),
                            bareme=question_data.get('bareme', 1),
                            reponse_ia=question_data.get('reponse_ia', '')
                        )
            
            # Recalcul du barème total
            total_points = sum(question.bareme for question in evaluation.questions.all())
            evaluation.bareme_total = total_points
            evaluation.save()
            
            # Retourner l'évaluation mise à jour
            return Response(EvaluationSerializer(evaluation).data)
        
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'évaluation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            if request.user.role != 'PROFESSEUR':
                return Response({"error": "Seuls les professeurs peuvent modifier des évaluations"},
                            status=status.HTTP_403_FORBIDDEN)
            
            evaluation = self.get_object()
            professeur = Professeur.objects.get(user=request.user)
            
            # Vérifier que le professeur est bien responsable de cette évaluation
            if evaluation.matiere.professeur != professeur:
                return Response({"error": "Vous n'êtes pas responsable de cette évaluation"},
                            status=status.HTTP_403_FORBIDDEN)
            
            # Récupérer les données du formulaire
            matiere_id = request.data.get('matiere_id')
            try:
                matiere = Matiere.objects.get(id=matiere_id, professeur=professeur)
            except Matiere.DoesNotExist:
                return Response({"error": "Matière non trouvée ou non autorisée"},
                            status=status.HTTP_400_BAD_REQUEST)
            
            fichier = request.FILES.get('fichier')
            format_fichier = request.data.get('format')
            titre = request.data.get('titre')
            date_evaluation = request.data.get('date_evaluation', now().date())
            
            if not fichier or format_fichier not in ['pdf', 'text', 'latex']:
                return Response({"error": "Format de fichier non supporté"},
                            status=status.HTTP_400_BAD_REQUEST)
            
            # Supprimer l'ancien fichier
            if evaluation.fichier:
                default_storage.delete(evaluation.fichier.name)
            
            # Sauvegarder le nouveau fichier
            file_path = default_storage.save(f"evaluations/{now().strftime('%Y%m%d_%H%M%S')}_{fichier.name}", fichier)
            
            # Extraire le contenu du fichier
            contenu = extract_text(default_storage.path(file_path), format_fichier)
            
            # Mettre à jour l'évaluation
            evaluation.matiere = matiere
            evaluation.titre = titre
            evaluation.fichier = file_path
            evaluation.format = format_fichier
            evaluation.date_evaluation = date_evaluation
            evaluation.sujet = contenu
            evaluation.save()
            
            # Supprimer les anciennes questions
            evaluation.questions.all().delete()
            
            # Extraire et créer les nouvelles questions
            questions_text = re.findall(r"(\d+[\)\.-]\s?.*?)(?=(\d+[\)\.-]|$))", contenu, re.S)
            total_points = 0
            
            for match in questions_text:
                question_text = match[0].strip()
                points = re.search(r"\((\d+)\s?pts?\)", question_text, re.I)
                bareme = int(points.group(1)) if points else 1
                reponse = ask_deepseek(question_text)
                
                Question.objects.create(
                    evaluation=evaluation,
                    contenu=question_text,
                    bareme=bareme,
                    reponse_ia=reponse
                )
                total_points += bareme
            
            # Mettre à jour le barème total
            evaluation.bareme_total = total_points
            evaluation.save()
            
            return Response(EvaluationSerializer(evaluation).data)
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'évaluation: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        
class ReponseEleveViewSet(viewsets.ModelViewSet):
    serializer_class = ReponseEleveSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'ADMIN':
            return ReponseEleve.objects.all()
        if user.role == 'PROFESSEUR':
            return ReponseEleve.objects.filter(evaluation__matiere__professeur__user=user)
        if user.role == 'ETUDIANT':
            return ReponseEleve.objects.filter(etudiant__user=user)
        return ReponseEleve.objects.none()
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if request.user.role != 'ETUDIANT':
            return Response({"error": "Seuls les étudiants peuvent soumettre des réponses"},
                           status=status.HTTP_403_FORBIDDEN)
        
        try:
            etudiant = Etudiant.objects.get(user=request.user)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=status.HTTP_400_BAD_REQUEST)
        
        evaluation_id = request.data.get('evaluation_id')
        try:
            evaluation = Evaluation.objects.prefetch_related('questions').get(
                id=evaluation_id, 
                matiere__classe=etudiant.classe
            )
            date_evaluation=evaluation.date_evaluation
            if date_evaluation < now():
                return Response({"error": "La date d'évaluation est dépassée"}, 
                           status=status.HTTP_400_BAD_REQUEST)
        except Evaluation.DoesNotExist:
            return Response({"error": "Évaluation non trouvée ou non autorisée"}, 
                           status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier si l'étudiant a déjà soumis une réponse
        if ReponseEleve.objects.filter(etudiant=etudiant, evaluation=evaluation).exists():
            return Response({"error": "Vous avez déjà soumis une réponse pour cette évaluation"},
                           status=status.HTTP_400_BAD_REQUEST)
        
        fichier = request.FILES.get('fichier')
        format_fichier = request.data.get('format')
        
        if not fichier or format_fichier not in ['pdf', 'text', 'latex']:
            return Response({"error": "Format de fichier non supporté"}, 
                           status=status.HTTP_400_BAD_REQUEST)
        
        # Sauvegarder le fichier avec un nom unique
        file_path = default_storage.save(
            f"reponses/{evaluation.id}/{etudiant.id}/{now().strftime('%Y%m%d_%H%M%S')}_{fichier.name}", 
            fichier
        )
        
        # Créer l'objet réponse élève
        reponse_eleve = ReponseEleve.objects.create(
            etudiant=etudiant,
            evaluation=evaluation,
            fichier=file_path,
            format=format_fichier,
            status="CORRIGÉ",
        )
        
        # Extraction du texte du fichier
        try:
            contenu = extract_text(default_storage.path(file_path), format_fichier)
            if not contenu:
                raise ValueError("Impossible d'extraire le contenu du fichier.")
        except Exception as e:
            # Supprimer la réponse si l'extraction échoue
            reponse_eleve.delete()
            default_storage.delete(file_path)
            return Response(
                {"error": f"Erreur lors de l'extraction du contenu du fichier: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extraire les réponses de l'élève
        try:
            # Récupérer les questions dans l'ordre correct
            questions = list(evaluation.questions.all().order_by('id'))
            question_count = len(questions)
            
            # Extraire les réponses du fichier
            reponses_text = []
            
            # Méthode 1: Recherche par expression régulière des questions numérotées
            matches = re.findall(r"(\d+[\)\.-]\s?.*?)(?=(\d+[\)\.-]|$))", contenu, re.S)
            if matches:
                for match in matches:
                    reponses_text.append(match[0].strip())
            
            # Si le nombre de réponses trouvées ne correspond pas au nombre de questions,
            # utiliser une méthode alternative en divisant le contenu
            if not reponses_text or len(reponses_text) != question_count:
                # Méthode 2: Diviser le contenu par sections
                sections = re.split(r"\n{2,}", contenu)
                reponses_text = [section.strip() for section in sections if section.strip()]
            
            # Si nous avons toujours un problème de correspondance, utiliser le contenu entier
            if not reponses_text or len(reponses_text) != question_count:
                logger.warning(
                    f"Impossible de bien identifier les réponses. "
                    f"Trouvé {len(reponses_text)} réponses pour {question_count} questions."
                )
                
                # Diviser le contenu en parties égales
                contenu_parts = []
                contenu_length = len(contenu)
                part_size = contenu_length // question_count
                
                for i in range(question_count):
                    start = i * part_size
                    end = (i + 1) * part_size if i < question_count - 1 else contenu_length
                    contenu_parts.append(contenu[start:end].strip())
                
                reponses_text = contenu_parts
            
            # S'assurer que nous avons le bon nombre de réponses
            if len(reponses_text) < question_count:
                # Compléter avec des réponses vides si nécessaire
                reponses_text.extend([""] * (question_count - len(reponses_text)))
            elif len(reponses_text) > question_count:
                # Ne garder que les premières réponses correspondant au nombre de questions
                reponses_text = reponses_text[:question_count]
            
            # Traiter chaque question et sa réponse correspondante
            total_points, total_possible = 0, 0
            
            for i, question in enumerate(questions):
                reponse_text = reponses_text[i]
                
                # Nettoyer la réponse (supprimer le numéro de question s'il existe)
                if re.match(r"^\d+[\)\.-]", reponse_text):
                    reponse_text = re.sub(r"^\d+[\)\.-]\s*", "", reponse_text)
                
                # Évaluer la réponse par rapport à la référence IA
                try:
                    score = evaluate_student_answer(reponse_text, question.reponse_ia)
                except Exception as e:
                    logger.error(f"Erreur lors de l'évaluation de la réponse {i+1}: {str(e)}")
                    score = 0.5  # Note par défaut en cas d'erreur
                
                # Calculer la note pour cette question
                note_question = score * question.bareme
                
                # Créer l'objet de réponse à la question
                ReponseQuestion.objects.create(
                    reponse_eleve=reponse_eleve,
                    question=question,
                    contenu=reponse_text,
                    note=note_question
                )
                
                total_points += note_question
                total_possible += question.bareme
            
            # Calculer la note finale (sur 20)
            if total_possible > 0:
                note_finale = (total_points / total_possible) * 20
            else:
                note_finale = 0
            
            # Arrondir à deux décimales
            note_finale = round(note_finale, 2)
            
            # Mettre à jour la note de la réponse élève
            reponse_eleve.note = note_finale
            reponse_eleve.save()
            
            return Response(ReponseEleveSerializer(reponse_eleve).data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # En cas d'erreur, faire un rollback complet
            logger.error(f"Erreur lors du traitement des réponses: {str(e)}")
            # Supprimer la réponse et toutes les réponses aux questions associées
            reponse_eleve.delete()
            default_storage.delete(file_path)
            return Response(
                {"error": f"Erreur lors du traitement des réponses: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        reponse_eleve = self.get_object()
        
        # Vérifier les autorisations - seul le professeur de la matière ou un admin peut modifier les notes
        user = request.user
        if user.role == 'ETUDIANT':
            return Response({"error": "Les étudiants ne peuvent pas modifier les notes"},
                        status=status.HTTP_403_FORBIDDEN)
        
        if user.role == 'PROFESSEUR':
            # Vérifier que le professeur est bien responsable de cette matière
            if not reponse_eleve.evaluation.matiere.professeur.user == user:
                return Response({"error": "Vous n'êtes pas responsable de cette matière"},
                            status=status.HTTP_403_FORBIDDEN)
        
        try:
            # Mettre à jour la note globale si fournie
            if 'note' in request.data:
                reponse_eleve.note = request.data.get('note')
                reponse_eleve.save()
            
            # Mettre à jour les notes par question si fournies
            reponses_questions_data = request.data.get('reponses_questions', [])
            if reponses_questions_data:
                for reponse_question_data in reponses_questions_data:
                    reponse_question_id = reponse_question_data.get('id')
                    if not reponse_question_id:
                        continue
                    
                    try:
                        # Vérifier que la réponse question appartient bien à cette réponse élève
                        reponse_question = ReponseQuestion.objects.get(
                            id=reponse_question_id, 
                            reponse_eleve=reponse_eleve
                        )
                        
                        # Mettre à jour la note et éventuellement le contenu
                        if 'note' in reponse_question_data:
                            reponse_question.note = reponse_question_data['note']
                        
                        if 'contenu' in reponse_question_data:
                            reponse_question.contenu = reponse_question_data['contenu']
                        
                        reponse_question.save()
                        
                    except ReponseQuestion.DoesNotExist:
                        return Response(
                            {"error": f"Réponse question avec ID {reponse_question_id} non trouvée"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                # Recalculer la note globale automatiquement si demandé
                if request.data.get('recalculate_note', False):
                    questions = reponse_eleve.evaluation.questions.all()
                    total_bareme = sum(question.bareme for question in questions)
                    
                    if total_bareme > 0:
                        total_points = sum(reponse_question.note for reponse_question in reponse_eleve.reponses_questions.all())
                        note_finale = (total_points / total_bareme) * 20
                        reponse_eleve.note = round(note_finale, 2)
                        reponse_eleve.save()
            
            # Renvoyer les données mises à jour
            return Response(ReponseEleveSerializer(reponse_eleve).data)
        
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des notes: {str(e)}")
            return Response(
                {"error": f"Erreur lors de la mise à jour des notes: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )