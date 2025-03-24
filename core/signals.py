from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(post_migrate)
def create_admin_user(sender, **kwargs):
    if sender.name == 'core':
        # Créer un utilisateur admin si aucun n'existe
        if not User.objects.filter(email='c').exists():
            admin = User.objects.create_superuser( 
                email='moussandoye@gmail.com',
                password='passer',
            )
            print(f"Admin user created: {admin.email}")
