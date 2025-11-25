from django.contrib import admin
from .models import School, Subscription, SchoolUser

# Registrar escola
@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner')
    prepopulated_fields = {"slug": ("name",)}  # gera automaticamente o slug

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # adiciona o owner como SchoolUser admin se ainda não existir
        if not SchoolUser.objects.filter(user=obj.owner, school=obj).exists():
            SchoolUser.objects.create(user=obj.owner, school=obj, role='admin')


# Registrar assinatura
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('school', 'plan', 'start_date', 'end_date', 'active')
    list_filter = ('plan', 'active')



# Registrar Alunos na escola
@admin.register(SchoolUser)
class SchoolUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'school', 'role')
    list_filter = ('school', 'role')
    search_fields = ('user__username', 'school__name')

