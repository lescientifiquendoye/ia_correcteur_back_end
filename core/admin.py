from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    User, RegisteredEmail, Classe, Professeur, Etudiant, Matiere, 
    Evaluation, Question, ReponseEleve, ReponseQuestion
)

class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Permissions'), {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )
    search_fields = ('email',)
    ordering = ('email',)

admin.site.register(User, UserAdmin)
admin.site.register(RegisteredEmail)
admin.site.register(Classe)
admin.site.register(Professeur)
admin.site.register(Etudiant)
admin.site.register(Matiere)
admin.site.register(Evaluation)
admin.site.register(Question)
admin.site.register(ReponseEleve)
admin.site.register(ReponseQuestion)