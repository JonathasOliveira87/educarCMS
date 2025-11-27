import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q, Avg, Sum
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from .models import School, SchoolUser, Course, Category, Profile, Certificate, Subject, Lesson, Progress, Enrollment, LessonVideo
from .helpers import get_course_duration, get_school_duration, mark_lesson_as_completed, themed_template, human_short, estimate_duration, update_course_duration, t
from django.db import IntegrityError, transaction
from .decorators import school_context_required, admin_required
import random
from django.core.files.storage import FileSystemStorage
from django.views.decorators.http import require_POST
from django.db.models import Prefetch


User = get_user_model()


# ============================================================
# HOME (PUBLICO)
# ============================================================
def portal_home(request):
    # lista de escolas para o template
    schools = School.objects.all()

    # indicadores agregados
    schools_count = schools.count()

    # Estudantes
    students_count = SchoolUser.objects.filter(role='student').count()
    active_students_count = SchoolUser.objects.filter(role='student', user__is_active=True).count()

    # Professores
    teachers_count = SchoolUser.objects.filter(role='teacher').count()
    active_teachers_count = SchoolUser.objects.filter(role='teacher', user__is_active=True).count()


    context = {
        'schools': schools,
        'stats': {
            'schools_count': schools_count,
            'schools_count_fmt': human_short(schools_count),
            'students_count': students_count,
            'students_count_fmt': human_short(students_count),
            'active_students_count': active_students_count,
            'active_students_count_fmt': human_short(active_students_count),
            'teachers_count': teachers_count,
            'teachers_count_fmt': human_short(teachers_count),
            'active_teachers_count': active_teachers_count,
            'active_teachers_count_fmt': human_short(active_teachers_count),
        }
    }
    return render(request, 'portal_home.html', context)


# ============================================================
# LOGIN (PUBLICO)
# ============================================================
def auth_login_or_dashboard(request, slug):
    school = get_object_or_404(School, slug=slug)
    template_name = themed_template(school, "login")

    # Se já está logado e pertence à escola
    if request.user.is_authenticated:
        if SchoolUser.objects.filter(user=request.user, school=school).exists():
            return redirect('school_dashboard', slug=slug)
        else:
            logout(request)
            messages.warning(request, f"Você estava logado em outra escola. Faça login em {school.name}.")
            return redirect('auth_login', slug=slug)

    next_url = request.GET.get('next', reverse('school_dashboard', kwargs={'slug': slug}))

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if not user:
            messages.error(request, "Usuário ou senha incorretos.")
        elif not user.is_active:
            messages.error(request, "Conta inativa. Contate o administrador.")
        elif not SchoolUser.objects.filter(user=user, school=school).exists():
            messages.error(request, "Usuário não pertence a esta escola.")
        else:
            login(request, user)
            return redirect(next_url)

    return render(request, template_name, {'school': school, 'next': next_url})


# ============================================================
# DASHBOARD (PARA AUTENTICADOS)  (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def school_dashboard(request, slug, school_user, school):
    now = timezone.now()

    # === CURSOS ===
    all_courses = Course.objects.filter(school=school).annotate(
        num_lessons=Count('subjects__lessons', distinct=True),
        num_students=Count('enrollments', distinct=True)
    )

    # Cursos ativos
    active_courses = all_courses.filter(status='active')
    
    # Cursos em destaque
    featured = all_courses.filter(is_featured=True)

    # Cursos recentes (5 mais novos)
    recent_courses = all_courses.order_by('-created_at')[:5]

    # Últimas atividades
    last_course = all_courses.order_by('-created_at').first()

    last_lesson = Lesson.objects.filter(
        subjects__course__school=school
    ).order_by('-created_at').first()


    # === ALUNOS ===
    all_students = SchoolUser.objects.filter(school=school, role='student')
    last_student = all_students.order_by('-created_at').first()

    # === PROGRESSO GERAL DA ESCOLA ===
    school_progress_avg = Progress.objects.filter(
        course__school=school
    ).aggregate(avg=Avg('progress_percentage'))['avg'] or 0

    school_progress_avg = round(school_progress_avg, 0)


    # Totais
    students_total = all_students.count()
    courses_total = all_courses.count()
    lessons_total = Lesson.objects.filter(school=school).count()
    school_duration = get_school_duration(school, published_only=True)

    context = {
        'school': school,
        'school_user': school_user,
        'all_courses': all_courses,
        'active_courses': active_courses,
        'recent_courses': recent_courses,
        'last_course': last_course,
        'last_lesson': last_lesson,
        'last_student': last_student,
        'school_progress_avg': school_progress_avg,
        'students_total': students_total,
        'courses_total': courses_total,
        'lessons_total': lessons_total,
        'school_duration':school_duration,
        'featured':featured
    }

    return t(request, school, "dashboard", context)



# ============================================================
# LOGOUT (ALUNO / PROFESSOR / ADMIN)
# ============================================================
def auth_logout(request, slug):
    logout(request)
    return redirect('auth_login', slug=slug)



# ============================================================
# CRIAR MATÉRIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def subject_create(request, slug, course_id, school_user, school):
    """
    Cria uma nova matéria (somente administradores)
    """
    course = get_object_or_404(Course, id=course_id, school=school)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        order = request.POST.get('order', 1)
        status = request.POST.get('status', 'draft')

        if not title:
            messages.error(request, "O título da matéria é obrigatório.")
            return redirect('course_detail', slug=slug, course_id=course.id)

        Subject.objects.create(
            course=course,
            title=title,
            description=description,
            order=order,
            status=status
        )

        messages.success(request, f'Matéria "{title}" criada com sucesso!')
        return redirect('course_detail', slug=slug, course_id=course.id)

    messages.warning(request, "Requisição inválida.")
    return redirect('course_detail', slug=slug, course_id=course.id)


# ============================================================
# ATUALIZAR MATÉRIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def subject_update(request, slug, course_id, subject_id, school_user, school):
    """
    Atualiza os dados de uma matéria existente (somente administradores)
    """
    course = get_object_or_404(Course, id=course_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=course)

    if request.method == 'POST':
        subject.title = request.POST.get('title', subject.title).strip()
        subject.description = request.POST.get('description', subject.description).strip()
        subject.order = request.POST.get('order', subject.order)
        subject.status = request.POST.get('status', subject.status)
        subject.save()

        messages.success(request, f'A matéria "{subject.title}" foi atualizada com sucesso!')
        return redirect('course_detail', slug=slug, course_id=course.id)

    messages.error(request, 'Erro ao atualizar a matéria.')
    return redirect('course_detail', slug=slug, course_id=course.id)

# ============================================================
# EXCLUIR MATÉRIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def subject_delete(request, slug, course_id, subject_id, school_user, school):
    """
    Exclui uma matéria (somente administradores)
    """
    course = get_object_or_404(Course, id=course_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=course)

    if request.method == 'POST':
        title = subject.title
        subject.delete()
        messages.success(request, f'A matéria "{title}" foi excluída com sucesso!')
        return redirect('course_detail', slug=slug, course_id=course.id)

    messages.error(request, "A exclusão deve ser feita por POST.")
    return redirect('course_detail', slug=slug, course_id=course.id)


# ============================================================
# Progresso do Curso (Percentual do Aluno)(concluídas / total) * 100
# ============================================================
def calculate_course_progress(student, course):
    """Progresso real do curso (aulas publicadas concluídas / total publicadas)."""

    published_lessons = Lesson.objects.filter(
        subjects__course=course,
        status="published"
    ).distinct()

    total_lessons = published_lessons.count()
    if total_lessons == 0:
        return 0

    completed_lessons = Progress.objects.filter(
        student=student,
        course=course,
        lesson__in=published_lessons,
        is_completed=True
    ).count()

    return round((completed_lessons / total_lessons) * 100, 1)

# ============================================================
# 
# ============================================================
def calculate_subject_progress(student, subject):
    """Progresso do aluno na matéria (somente aulas publicadas contam)."""

    # Só aulas publicadas entram no cálculo
    published_lessons = subject.lessons.filter(status="published")

    total_lessons = published_lessons.count()
    if total_lessons == 0:
        return 0

    completed_lessons = Progress.objects.filter(
        student=student,
        lesson__in=published_lessons,
        is_completed=True
    ).count()

    return round((completed_lessons / total_lessons) * 100, 1)

def calculate_user_course_progress(student, course):
    """Progresso real do aluno no curso (aulas publicadas concluídas / total publicadas)."""

    # Todas as lessons publicadas do curso
    published_lessons = Lesson.objects.filter(
        subjects__course=course,
        status="published"
    ).distinct()

    total_lessons = published_lessons.count()
    if total_lessons == 0:
        return 0

    completed_lessons = Progress.objects.filter(
        student=student,
        course=course,
        lesson__in=published_lessons,
        is_completed=True
    ).count()

    return round((completed_lessons / total_lessons) * 100, 1)





    
# ============================================================
# GERENCIAR USUÁRIOS DA ESCOLA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def manage_users(request, slug, school_user, school):
    """
    Lista e gerencia os usuários da escola (somente administradores ou o dono).
    """
    # --------------------------------------------
    # Contadores GLOBAIS (antes do filtro)
    # --------------------------------------------
    all_users = SchoolUser.objects.filter(school=school)

    total_students = all_users.filter(role="student").count()
    total_teachers = all_users.filter(role="teacher").count()
    total_admins = all_users.filter(
        Q(role="admin") | Q(user__is_superuser=True)
    ).count()
    total_inactive = all_users.filter(user__is_active=False).count()
    total_users = all_users.count()
    active_users = all_users.filter(user__is_active=True).count()
    # --------------------------------------------
    # FILTRO
    # --------------------------------------------
    filter_type = request.GET.get("filter", "all")
    school_users = all_users

    if filter_type == "students":
        school_users = school_users.filter(role="student")

    elif filter_type == "teachers":
        school_users = school_users.filter(role="teacher")

    elif filter_type == "admins":
        school_users = school_users.filter(
            Q(role="admin") | Q(user__is_superuser=True)
        )

    elif filter_type == "inactive":
        school_users = school_users.filter(user__is_active=False)

    # --------------------------------------------
    # PAGINAÇÃO
    # --------------------------------------------
    paginator = Paginator(school_users.order_by('-created_at'), 7)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)



    now = timezone.now()
    new_this_month = school_users.filter(
        created_at__year=now.year,
        created_at__month=now.month
    ).count()

    context = {
        'school': school,
        'school_user': school_user,
        'page_obj': page_obj,
        'active_users': active_users,
        'new_this_month': new_this_month,
        'filter_type': filter_type,

        # Totais
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_admins': total_admins,
        'total_inactive': total_inactive,
        'total_users': total_users,
    }

    return render(request, themed_template(school, "manage_users"), context)


# ============================================================
# CRIAR NOVO USUÁRIO (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
@transaction.atomic
def create_user(request, slug, school_user, school):
    """
    Cria um novo usuário vinculado à escola (somente administradores ou o dono).
    """
    if request.method == 'POST':
        full_name = request.POST.get("full_name")
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        role = request.POST.get('role')
        status = request.POST.get('status') == 'active'
        password = request.POST.get('password') or '123456'

        # 🔹 Validações básicas
        if not username or not full_name or not email or not phone or not role:
            messages.error(request, "Preencha todos os campos obrigatórios.")
            return redirect('manage_users', slug=slug)

        if not username.isdigit() or len(username) != 7:
            messages.error(request, "RU inválido. Deve conter 7 números.")
            return redirect('manage_users', slug=slug)

        if User.objects.filter(username=username).exists():
            messages.error(request, f"O RU {username} já está em uso.")
            return redirect('manage_users', slug=slug)

        if User.objects.filter(email=email).exists():
            messages.error(request, "Esse email já está cadastrado.")
            return redirect('manage_users', slug=slug)

        # 🔹 Divide nome
        parts = full_name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 🔹 Cria usuário base
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )
        user.is_active = status
        user.save()

        # 🔹 Cria perfil e vínculo
        Profile.objects.create(
            user=user,
            phone=phone,
            theme='light',
            language='pt-BR',
            public_profile=True,
            show_progress=True,
            email_messages=True,
            email_course_updates=True,
        )

        SchoolUser.objects.create(
            user=user,
            school=school,
            role=role,
            phone=phone
        )

        messages.success(request, f'Usuário "{full_name}" criado com sucesso! RU: {username}')
        return redirect('manage_users', slug=slug)

    messages.warning(request, "Requisição inválida.")
    return redirect('manage_users', slug=slug)


# ============================================================
# EDITAR USUÁRIO EXISTENTE (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
@transaction.atomic
def edit_user(request, slug, user_id, school_user, school):
    """
    Edita dados de um usuário existente (somente administradores ou o dono).
    """
    su = get_object_or_404(SchoolUser, id=user_id, school=school)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', '').strip()
        status = request.POST.get('status') == 'active'

        first_name, *last_name_parts = full_name.split(' ', 1)
        last_name = last_name_parts[0] if last_name_parts else ''

        su.user.first_name = first_name
        su.user.last_name = last_name
        su.user.email = email
        su.user.is_active = status
        su.user.save()

        su.phone = phone
        su.role = role
        su.save()

        if hasattr(su.user, 'profile'):
            su.user.profile.phone = phone
            su.user.profile.save()

        messages.success(request, f'Usuário "{full_name}" atualizado com sucesso!')
        return redirect('manage_users', slug=slug)

    return render(request, themed_template(school, "edit_user"), {
        'school': school,
        'school_user': school_user,
        'su': su,
    })


# ============================================================
# EXCLUIR USUÁRIO (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
@transaction.atomic
def delete_user(request, slug, user_id, school_user, school):
    """
    Exclui completamente o usuário da escola (somente administradores ou o dono).
    """
    su = get_object_or_404(SchoolUser, id=user_id, school=school)
    name = su.user.get_full_name() or su.user.username

    su.user.delete()
    messages.success(request, f'Usuário "{name}" removido com sucesso.')
    return redirect('manage_users', slug=slug)
