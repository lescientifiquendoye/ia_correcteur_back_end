from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, Group, Permission
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

class UserManager(BaseUserManager):
    def create_user(self, email, password=None,**extra_fields):
        if not email:
            raise ValueError('L\'adresse email est obligatoire')
        
        email = self.normalize_email(email)
        user = self.model(email=email,**extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password ,**extra_fields)

class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Administrateur'),
        ('PROFESSEUR', 'Professeur'),
        ('ETUDIANT', 'Étudiant'),
    )
    
    username = None
    email = models.EmailField(_('adresse email'), unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='ETUDIANT')
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    objects = UserManager()

    
   

    def __str__(self):
        return self.email


class Classe(models.Model):
    NIVEAU_CHOICES = (
        ('L1', 'licence 1'),
        ('L2', 'licence 2'),
        ('L3', 'licence 3'),
        ('M1', 'master 1'),
        ('M2', 'master 2'),
    )
    nom = models.CharField(max_length=50, unique=True)
    niveau = models.CharField(max_length=4,choices=NIVEAU_CHOICES, default='L1')

    def __str__(self):
       return f"{self.nom} ({self.niveau}) "
    

class RegisteredEmail(models.Model):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=User.ROLE_CHOICES)
    is_registered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='registered_emails',default=None, blank=True, null=True)
    
    def __str__(self):
        return f"{self.email} ({self.role}) ({self.classe})"


class Professeur(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='professeur')
    nom = models.CharField(max_length=50)
    prenom = models.CharField(max_length=50)
    
    def __str__(self):
        return f"{self.prenom} {self.nom}"

class Etudiant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='etudiant')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='etudiants')
    nom = models.CharField(max_length=50)
    prenom = models.CharField(max_length=50)
    
    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.classe})"

class Matiere(models.Model):
    professeur = models.ForeignKey(Professeur, on_delete=models.CASCADE, related_name='matieres')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='matieres')
    intitule = models.CharField(max_length=100)
    coefficient = models.DecimalField(max_digits=3, decimal_places=2)
    
    def __str__(self):
        return f"{self.intitule} ({self.classe})"

class Evaluation(models.Model):
    FORMAT_CHOICES = (
        ('pdf', 'PDF'),
        ('text', 'Texte'),
        ('latex', 'LaTeX'),
    )
    
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, related_name='evaluations')
    titre = models.CharField(max_length=100)
    sujet = models.TextField(blank=True)
    fichier = models.FileField(upload_to='evaluations/')
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES)
    date_creation = models.DateTimeField(default=timezone.now)
    date_evaluation = models.DateTimeField(default=timezone.now)
    bareme_total = models.IntegerField(default=20)
    
    def __str__(self):
        return f"{self.titre} ({self.matiere})"

class Question(models.Model):
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='questions')
    contenu = models.TextField()
    bareme = models.IntegerField()
    reponse_ia = models.TextField(blank=True)
    
    def __str__(self):
        return f"Question {self.id} - {self.evaluation.titre}"

class ReponseEleve(models.Model):
    FORMAT_CHOICES = (
        ('pdf', 'PDF'),
        ('text', 'Texte'),
        ('latex', 'LaTeX'),
    )
    
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='reponses')
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='reponses_eleves')
    fichier = models.FileField(upload_to='reponses/')
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES)
    date_soumission = models.DateTimeField(default=timezone.now)
    note = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, default='EN ATTENTE')
    
    def __str__(self):
        return f"Réponse de {self.etudiant} pour {self.evaluation.titre} ({self.status}) ({self.note})"

class ReponseQuestion(models.Model):
    reponse_eleve = models.ForeignKey(ReponseEleve, on_delete=models.CASCADE, related_name='reponses_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='reponses_eleves')
    contenu = models.TextField()
    note = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    
    
    def __str__(self):
        return f"Réponse à Q{self.question.id} - {self.reponse_eleve.etudiant}"
