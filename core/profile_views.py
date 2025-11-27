# ============================
# DJANGO IMPORTS
# ============================
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_POST

# ============================
# MODELS
# ============================
from .models import Course, Profile, Certificate

# ============================
# HELPERS
# ============================
from .helpers import themed_template, t

# ============================
# DECORATORS
# ============================
from .decorators import school_context_required



# ============================================================
# PERFIL DO USUÁRIO (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile(request, slug, *args, **kwargs):

    # ------------------------------------------------------------
    # 1. Contexto da escola e do usuário dentro da escola
    # ------------------------------------------------------------
    school_user = kwargs.get("school_user")
    school = kwargs.get("school")

    # ------------------------------------------------------------
    # 2. Perfil global do usuário (Profile)
    # ------------------------------------------------------------
    profile, _ = Profile.objects.get_or_create(user=request.user)

    # ------------------------------------------------------------
    # 3. Cursos em que o usuário está matriculado
    # ------------------------------------------------------------
    enrolled_courses = Course.objects.filter(
        enrollments__student=school_user,
        school=school
    ).distinct()

    # ------------------------------------------------------------
    # 4. Contagem de cursos concluídos
    # ------------------------------------------------------------
    completed_courses_count = enrolled_courses.filter(
        enrollments__status='completed'
    ).count()

    # ------------------------------------------------------------
    # 5. Certificados emitidos para o usuário (corrigido: student é User)
    # ------------------------------------------------------------
    certificates = Certificate.objects.filter(
        student=school_user.user,
        course__school=school
    )
    certificates_count = certificates.count()

    # ------------------------------------------------------------
    # 6. Contexto final enviado ao template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'profile': profile,
        'enrolled_courses': enrolled_courses,
        'completed_courses_count': completed_courses_count,
        'certificates': certificates,
        'certificates_count': certificates_count,
    }

    # ------------------------------------------------------------
    # 7. Renderiza o template temático correto
    # ------------------------------------------------------------
    return t(request, school, "profile", context)


# ============================================================
# ATUALIZAR INFORMAÇÕES PESSOAIS (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile_update(request, slug, school_user, school):

    # ------------------------------------------------------------
    # 1. Apenas POST é permitido
    # ------------------------------------------------------------
    if request.method == 'POST':

        # --------------------------------------------------------
        # 1.1 Atualiza dados básicos do usuário
        # --------------------------------------------------------
        user = request.user
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', user.email).strip()
        user.save()

        # --------------------------------------------------------
        # 1.2 Atualiza dados adicionais do perfil
        # --------------------------------------------------------
        profile, _ = Profile.objects.get_or_create(user=user)

        profile.phone = request.POST.get('phone', '').strip()
        profile.bio = request.POST.get('bio', '').strip()
        profile.birth_date = request.POST.get('birth_date') or None
        profile.gender = request.POST.get('gender', '').strip()
        profile.location = request.POST.get('location', '').strip()

        # Redes sociais
        profile.twitter = request.POST.get('twitter', '').strip()
        profile.linkedin = request.POST.get('linkedin', '').strip()
        profile.github = request.POST.get('github', '').strip()

        profile.save()

        # --------------------------------------------------------
        # 1.3 Mensagem de sucesso
        # --------------------------------------------------------
        messages.success(request, 'Perfil atualizado com sucesso!')

    # ------------------------------------------------------------
    # 2. Redireciona de volta para o perfil
    # ------------------------------------------------------------
    return redirect('profile', slug=slug)


# ============================================================
# PREFERÊNCIAS DE PERFIL (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile_preferences(request, slug, school_user, school):

    # ------------------------------------------------------------
    # 1. Apenas método POST é aceito
    # ------------------------------------------------------------
    if request.method == 'POST':

        # --------------------------------------------------------
        # 1.1 Carrega ou cria o perfil
        # --------------------------------------------------------
        profile, _ = Profile.objects.get_or_create(user=request.user)

        # --------------------------------------------------------
        # 1.2 Atualiza preferências
        # --------------------------------------------------------
        profile.theme = request.POST.get('theme', 'light')
        profile.public_profile = request.POST.get('public_profile') == 'on'
        profile.show_progress = request.POST.get('show_progress') == 'on'

        profile.save()

        # --------------------------------------------------------
        # 1.3 Mensagem de sucesso
        # --------------------------------------------------------
        messages.success(request, 'Preferências atualizadas com sucesso!')

    # ------------------------------------------------------------
    # 2. Redireciona de volta ao perfil
    # ------------------------------------------------------------
    return redirect('profile', slug=slug)


# ============================================================
# NOTIFICAÇÕES (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile_notifications(request, slug, school_user, school):

    # ------------------------------------------------------------
    # 1 Apenas método POST é aceito
    # ------------------------------------------------------------
    if request.method == 'POST':

        # --------------------------------------------------------
        # 1.1 Carrega ou cria o perfil
        # --------------------------------------------------------
        profile, _ = Profile.objects.get_or_create(user=request.user)

        # --------------------------------------------------------
        # 1.2 Atualiza preferências de notificações
        # --------------------------------------------------------
        profile.email_messages = request.POST.get('email_messages') == 'on'
        profile.email_course_updates = request.POST.get('email_course_updates') == 'on'
        profile.email_marketing = request.POST.get('email_marketing') == 'on'
        profile.push_notifications = request.POST.get('push_notifications') == 'on'

        profile.save()

        # --------------------------------------------------------
        # 1.3 Mensagem de sucesso
        # --------------------------------------------------------
        messages.success(request, 'Preferências de notificação atualizadas!')

    # ------------------------------------------------------------
    # 2. Redireciona de volta ao perfil
    # ------------------------------------------------------------
    return redirect('profile', slug=slug)


# ============================================================
# UPLOAD DE AVATAR (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile_avatar_upload(request, slug, school_user, school):

    # ------------------------------------------------------------
    # 1. Apenas aceita POST com arquivo de avatar
    # ------------------------------------------------------------
    if request.method == 'POST' and request.FILES.get('avatar'):

        # --------------------------------------------------------
        # 1.1 Carrega ou cria o perfil
        # --------------------------------------------------------
        profile, _ = Profile.objects.get_or_create(user=request.user)

        # --------------------------------------------------------
        # 1.2 Atualiza avatar
        # --------------------------------------------------------
        profile.avatar = request.FILES['avatar']
        profile.save()

        # --------------------------------------------------------
        # 1.3 Resposta de sucesso (usada por AJAX)
        # --------------------------------------------------------
        return JsonResponse({
            'success': True,
            'avatar_url': profile.avatar.url
        })

    # ------------------------------------------------------------
    # 2. Retorna erro caso algo inválido seja enviado
    # ------------------------------------------------------------
    return JsonResponse({'success': False}, status=400)


# ============================================================
# UPLOAD DE BANNER (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def profile_banner_upload(request, slug, school_user, school):
    """
    Upload de banner do perfil
    """
    if request.method == 'POST' and request.FILES.get('banner'):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.banner = request.FILES['banner']
        profile.save()

        return JsonResponse({
            'success': True,
            'message': t("Banner atualizado com sucesso!"),
            'banner_url': profile.banner.url
        })

    return JsonResponse({
        'success': False,
        'message': t("Erro ao enviar o banner. Tente novamente.")
    }, status=400)


# ============================================================
# ALTERAR SENHA (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def change_password(request, slug, school_user, school):
    """
    Altera senha do usuário
    """
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not request.user.check_password(current_password):
            messages.error(request, t('Senha atual incorreta.'))
            return redirect('profile', slug=slug)

        if new_password != confirm_password:
            messages.error(request, t('As senhas não coincidem.'))
            return redirect('profile', slug=slug)

        request.user.set_password(new_password)
        request.user.save()

        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)

        messages.success(request, t('Senha alterada com sucesso!'))

    return redirect('profile', slug=slug)
