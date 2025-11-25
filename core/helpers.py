from django.shortcuts import get_object_or_404, render
from django.db.models import Count, Q
from django.contrib.auth.models import User
from .models import School, SchoolUser
import random
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
import math
from .models import Lesson
from django.db.models import Sum
from django.utils import timezone
from core.models import Progress

# ============================================================
#  TEMA (templates por escola)
# ============================================================
def themed_template(school, template_name: str) -> str:
    """
    Retorna o caminho do template baseado no tema da escola.
    🔹 Verifica se o template do tema existe.
    🔹 Se não existir, cai para o tema default.
    🔹 Se nem o default existir, lança erro real.
    """
    theme = getattr(school, "theme", None) or "moder_htmx"

    themed_path = f"themes/{theme}/pages/{template_name}.html"

    try:
        get_template(themed_path)  # verifica template no tema da escola
        return themed_path
    except TemplateDoesNotExist:
        # tenta fallback no tema 'default'
        default_path = f"themes/default/pages/{template_name}.html"
        try:
            get_template(default_path)
            return default_path
        except TemplateDoesNotExist:
            # nenhum dos temas tem o template → erro real
            raise TemplateDoesNotExist(
                f"Template '{template_name}.html' não encontrado "
                f"em 'themes/{theme}' nem em 'themes/default'."
            )


def t(request, school, path, context=None):
    """
    Renderizador temático simplificado.
    🔹 Usa o tema da escola automaticamente.
    🔹 path = nome do template sem .html.
    🔹 Exemplo: t(request, school, "dashboard", context)
    """
    template = themed_template(school, path)
    return render(request, template, context or {})


# ============================================================
#  USUÁRIOS E ESCOLAS
# ============================================================
def get_school_user(slug, user):
    """
    Retorna o SchoolUser do usuário dentro da escola atual.
    🔹 Se o vínculo não existir, retorna None.
    🔹 Usado pelo decorator @school_context_required.
    """
    school = get_object_or_404(School, slug=slug)

    try:
        return SchoolUser.objects.get(user=user, school=school)
    except SchoolUser.DoesNotExist:
        return None


def create_school_user(user, school, role='student'):
    """
    Cria um SchoolUser para a escola se ainda não existir.
    🔹 Retorna o objeto (existente ou recém-criado).
    🔹 Roles possíveis: admin, teacher, student.
    """
    school_user, created = SchoolUser.objects.get_or_create(
        user=user,
        school=school,
        defaults={'role': role}
    )
    return school_user


# ============================================================
#  ESTATÍSTICAS DE CURSOS E USUÁRIOS
# ============================================================
def course_stats(courses_queryset):
    """
    Estatísticas gerais dos cursos:
    🔹 total → todos
    🔹 active → publicados
    🔹 draft → rascunhos
    🔹 archived → arquivados
    """
    return courses_queryset.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        draft=Count('id', filter=Q(status='draft')),
        archived=Count('id', filter=Q(status='archived'))
    )


def student_teacher_stats(school_users_queryset, role):
    """
    Estatísticas de alunos ou professores da escola:
    🔹 total
    🔹 ativos
    🔹 inativos
    🔹 criados no mês atual
    """
    now = timezone.now()
    qs = school_users_queryset.filter(role=role)
    return {
        'total': qs.count(),
        'active': qs.filter(user__is_active=True).count(),
        'inactive': qs.filter(user__is_active=False).count(),
        'new_this_month': qs.filter(
            user__date_joined__year=now.year,
            user__date_joined__month=now.month
        ).count(),
    }


# ============================================================
#  UTILITÁRIOS DIVERSOS
# ============================================================
def generate_unique_ru(length=6):
    """
    Gera RU (username numérico) único.
    🔹 Evita duplicados.
    🔹 Usado em cadastro rápido.
    """
    while True:
        ru = str(random.randint(10**(length-1), 10**length - 1))
        if not User.objects.filter(username=ru).exists():
            return ru


def human_short(n):
    """
    Formata números grandes para:
    🔹 1.2k+
    🔹 10k+
    🔹 1M+
    🔹 Se não for número, devolve string.
    """
    try:
        n = int(n)
    except Exception:
        return str(n)

    if n >= 1_000_000:
        return f"{math.floor(n/100000)/10 if n < 10_000_000 else math.floor(n/1000000)}M+"
    if n >= 1000:
        return f"{math.floor(n/1000)}k+"
    return str(n)


def estimate_duration(content_type, duration):
    """
    Determina a duração da aula:
    🔹 Se o form enviou a duração real, usa.
    🔹 Se não enviou, define por tipo:
        video → 30 min
        text → 5 min
        quiz → 3 min
        file → 2 min
    """
    try:
        duration_value = float(duration)
        if duration_value > 0:
            return duration_value
    except (TypeError, ValueError):
        pass

    default_durations = {
        'video': 30,
        'text': 5,
        'quiz': 3,
        'file': 2,
    }
    return default_durations.get(content_type, 0)


def update_course_duration(course):
    """
    Calcula a duração TOTAL do curso em horas.
    🔹 Soma todas as aulas ligadas às matérias do curso.
    🔹 Atualiza course.duration_hours automaticamente.
    """
    total_minutes = Lesson.objects.filter(
        subjects__course=course
    ).aggregate(total=Sum('duration'))['total'] or 0

    course.duration_hours = round(total_minutes / 60, 1)
    course.save(update_fields=["duration_hours"])


def mark_lesson_as_completed(student, course, lesson):
    """
    Marca a aula como concluída:
    🔹 Cria Progress se não existir.
    🔹 Atualiza porcentagem para 100%.
    🔹 Marca data de conclusão.
    """
    progress, _ = Progress.objects.get_or_create(
        student=student,
        course=course,
        lesson=lesson,
        defaults={
            "is_completed": True,
            "progress_percentage": 100,
            "completed_at": timezone.now(),
        },
    )

    progress.is_completed = True
    progress.progress_percentage = 100
    progress.completed_at = timezone.now()
    progress.save()

    return progress


def get_course_duration(course, published_only=False):
    """
    Retorna duração total do curso, considerando vídeos (LessonVideo) e outros tipos.
    """
    qs = Lesson.objects.filter(subjects__course=course)
    if published_only:
        qs = qs.filter(status="published")
    qs = qs.distinct()

    total_minutes = 0
    for lesson in qs:
        if lesson.content_type == 'video':
            # soma todos os vídeos da aula
            lesson_video_minutes = lesson.videos.aggregate(total=Sum('duration'))['total'] or 0
            total_minutes += float(lesson_video_minutes)
        else:
            total_minutes += float(lesson.duration or 0)

    h, m = divmod(total_minutes, 60)
    formatted = f"{int(h)}h {int(m)}min" if h else f"{int(m)}min"

    return {
        "minutes": total_minutes,
        "hours": int(h),
        "remaining": int(m),
        "formatted": formatted,
        "lessons": qs.count(),
    }


# ============================================================
#  DURAÇÃO TOTAL DA ESCOLA (todas as aulas)
# ============================================================
def get_school_duration(school, published_only=False):
    """
    Retorna informações de duração da ESCOLA:
    🔹 Soma TODAS as aulas da escola
    🔹 Pode filtrar somente publicadas
    🔹 Usa o MESMO padrão do get_course_duration()
    Retorna:
        minutes → total em minutos
        hours → horas inteiras
        remaining → minutos restantes
        formatted → string formatada (ex: 15h 20min)
        lessons → total de aulas
    """
    qs = Lesson.objects.filter(school=school)

    if published_only:
        qs = qs.filter(status="published")

    qs = qs.distinct()

    minutes = qs.aggregate(total=Sum("duration"))["total"] or 0

    h, m = divmod(minutes, 60)
    formatted = f"{h}h {m}min" if h else f"{m}min"

    return {
        "minutes": minutes,
        "hours": h,
        "remaining": m,
        "formatted": formatted,
        "lessons": qs.count(),
    }
