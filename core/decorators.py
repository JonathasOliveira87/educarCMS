from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.urls import reverse
from .helpers import get_school_user

def school_context_required(view_func):
    """
    🔹 Decorator que injeta automaticamente:
       - school_user (relacionamento do usuário com a escola)
       - school (objeto School)

    🔸 Uso:
        @school_context_required
        def my_view(request, slug, school_user, school):
            ...
    """
    @wraps(view_func)
    def wrapper(request, slug, *args, **kwargs):
        # Usuário não autenticado
        if not request.user.is_authenticated:
            next_url = request.get_full_path()
            login_url = reverse('auth_login', kwargs={'slug': slug})
            return redirect(f"{login_url}?next={next_url}")

        # Busca o vínculo do usuário com a escola
        school_user = get_school_user(slug, request.user)
        if not school_user:
            messages.error(request, "Você não tem acesso a esta escola.")
            return redirect("dashboard_home")

        school = school_user.school

        # Anexa ao request (útil em middlewares, logs ou templates)
        request.school_user = school_user
        request.school = school

        # Passa school_user e school pra view
        return view_func(request, slug, *args, school_user=school_user, school=school, **kwargs)

    return wrapper


def admin_required(view_func):
    """
    🔹 Restringe a view apenas para usuários com papel de 'admin' da escola.
    ⚠️ Requer o uso prévio de @school_context_required.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        school_user = getattr(request, 'school_user', None)
        school = getattr(request, 'school', None)

        # Se não houver school_user, provavelmente o decorator anterior faltou
        if not school_user or (school_user.role != 'admin' and request.user != school.owner):
            messages.error(request, "Apenas administradores ou o dono da escola podem acessar esta página.")
            return redirect('school_dashboard', slug=school.slug if school else 'home')

        # Se não for admin, bloqueia e mostra mensagem amigável
        if school_user.role != 'admin':
            messages.warning(request, "Apenas administradores podem acessar esta página.")
            return redirect('school_dashboard', slug=school.slug if school else 'home')

        # Permite o acesso normalmente
        return view_func(request, *args, **kwargs)

    return wrapper


def teacher_required(view_func):
    """
    🔹 Permite acesso apenas para:
        - admin
        - teacher

    🔹 Bloqueia:
        - student

    ⚠️ Requer o uso prévio de @school_context_required
       (pois depende de request.school_user)
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        school_user = getattr(request, 'school_user', None)
        school = getattr(request, 'school', None)

        # ⚠️ Caso school_context_required não tenha rodado
        if not school_user:
            messages.error(request, "Erro interno: contexto da escola não foi carregado.")
            return redirect("dashboard_home")

        # 🟢 Admin sempre pode acessar
        if school_user.role == "admin":
            return view_func(request, *args, **kwargs)

        # 🟢 Professor pode acessar
        if school_user.role == "teacher":
            return view_func(request, *args, **kwargs)

        # 🔴 Aluno não pode
        messages.warning(request, "Apenas professores têm acesso a esta página.")
        return redirect(
            "school_dashboard",
            slug=school.slug if school else "home"
        )

    return wrapper
