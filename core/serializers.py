from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    RegisteredEmail, Classe, Professeur, Etudiant, Matiere, 
    Evaluation, Question, ReponseEleve, ReponseQuestion
)

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'role')
        read_only_fields = ('role',)


class ClasseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classe
        fields = '__all__'

class RegisteredEmailSerializer(serializers.ModelSerializer):
    classe = ClasseSerializer(read_only=True)
    class Meta:
        model = RegisteredEmail
        fields = ('id', 'email', 'role', 'is_registered')

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    nom = serializers.CharField()
    prenom = serializers.CharField()
    classe_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate_email(self, value):
        try:
            registered_email = RegisteredEmail.objects.get(email=value, is_registered=False)
            return value
        except RegisteredEmail.DoesNotExist:
            raise serializers.ValidationError("Adresse email non autorisée à s'inscrire")

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()



class ProfesseurSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Professeur
        fields = '__all__'

class EtudiantSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    classe = ClasseSerializer(read_only=True)
    
    class Meta:
        model = Etudiant
        fields = '__all__'

class MatiereSerializer(serializers.ModelSerializer):
    professeur = ProfesseurSerializer(read_only=True)
    classe = ClasseSerializer(read_only=True)
    
    class Meta:
        model = Matiere
        fields = '__all__'

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = '__all__'
        read_only_fields = ('evaluation',)

class EvaluationSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    matiere = MatiereSerializer(read_only=True)
    matiere_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Evaluation
        fields = ('id', 'matiere', 'matiere_id', 'titre', 'sujet', 'fichier', 
                  'format', 'date_creation', 'date_evaluation', 'bareme_total', 'questions')

class ReponseQuestionSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    
    class Meta:
        model = ReponseQuestion
        fields = ('id', 'question', 'contenu', 'note')
        read_only_fields = ('reponse_eleve',)

class ReponseEleveSerializer(serializers.ModelSerializer):
    etudiant = EtudiantSerializer(read_only=True)
    evaluation = EvaluationSerializer(read_only=True)
    evaluation_id = serializers.IntegerField(write_only=True)
    reponses_questions = ReponseQuestionSerializer(many=True, read_only=True)
    class Meta:
        model = ReponseEleve
        fields = ('id', 'etudiant', 'evaluation', 'evaluation_id', 'fichier',
                 'format', 'date_soumission', 'note', 'reponses_questions', 'status')
        read_only_fields = ('etudiant', 'date_soumission')  