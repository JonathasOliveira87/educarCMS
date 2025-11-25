from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db.models import Count, Q, Avg, Sum, Prefetch
from django.core.paginator import Paginator
from .views import calculate_course_progress, calculate_user_course_progress
from .models import Assessment, Course, Category, Lesson, Progress, Enrollment
from .helpers import get_course_duration, t
from .decorators import school_context_required, admin_required, teacher_required

User = get_user_model()

# ============================================================
# COURSES (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def course_list(request, slug, school_user, school):
    """
    Lista todos os cursos da escola com filtros, busca,
    ordenação e paginação.
    Acesso exclusivo de administradores.
    """

    # ------------------------------------------------------------
    # 1. Query base com otimização + progresso médio
    # ------------------------------------------------------------
    courses = (
        Course.objects.filter(school=school)
        .select_related("category", "instructor")
        .prefetch_related("enrollments__student__user")
        .annotate(
            num_students=Count("enrollments", distinct=True),
            num_lessons=Count("subjects__lessons", distinct=True),
            avg_progress=Avg("student_progress__progress_percentage"),
        )
    )

    # ------------------------------------------------------------
    # 2. Filtro por status
    # ------------------------------------------------------------
    status_filter = request.GET.get("status", "all")
    if status_filter != "all":
        courses = courses.filter(status=status_filter)

    # ------------------------------------------------------------
    # 3. Busca por texto
    # ------------------------------------------------------------
    search_query = request.GET.get("search", "").strip()
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # ------------------------------------------------------------
    # 4. Ordenação
    # ------------------------------------------------------------
    sort_by = request.GET.get("sort", "recent")

    ordering_map = {
        "oldest": "created_at",
        "name": "title",
        "students": "-views_count",  # pode trocar depois pra num_students
        "recent": "-created_at",
    }
    courses = courses.order_by(ordering_map.get(sort_by, "-created_at"))

    # ------------------------------------------------------------
    # 5. Contadores globais
    # ------------------------------------------------------------
    all_courses = Course.objects.filter(school=school)
    context_counts = {
        "courses_count": all_courses.count(),
        "active_courses_count": all_courses.filter(status="active").count(),
        "draft_courses_count": all_courses.filter(status="draft").count(),
        "archived_courses_count": all_courses.filter(status="archived").count(),
    }

    # ------------------------------------------------------------
    # 6. Paginação
    # ------------------------------------------------------------
    paginator = Paginator(courses, 6)
    courses_page = paginator.get_page(request.GET.get("page", 1))

    # ------------------------------------------------------------
    # 7. Cálculo de duração / matérias / aulas por curso
    #     (igual ao course_detail, mas em loop)
    # ------------------------------------------------------------
    for c in courses_page.object_list:
        # subjects e lessons_qs equivalentes ao course_detail
        info = get_course_duration(c)
        c.total_duration_display = info["formatted"]
        c.total_lessons = info["lessons"]

    # ------------------------------------------------------------
    # 8. Contexto final
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "courses": courses_page,
        "current_status": status_filter,
        "current_sort": sort_by,
        "search_query": search_query,
        **context_counts,
    }

    # ------------------------------------------------------------
    # 9. Render com suporte a tema
    # ------------------------------------------------------------
    return t(request, school, "course/course_list", context)


# ============================================================
# DETALHE DO CURSO (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def course_detail(request, slug, course_id, school_user, school):
    """
    Página de detalhe do curso:
    - Admin/Teacher: vê tudo
    - Student: vê apenas conteúdos publicados
    - Exibe resumo, progresso, estatísticas e lista de matérias/aulas
    """

    # ------------------------------------------------------------
    # 1. Curso
    # ------------------------------------------------------------
    course = get_object_or_404(
        Course.objects.select_related("category", "instructor"),
        id=course_id,
        school=school
    )

    # ------------------------------------------------------------
    # 2. Subjects + Lessons (filtra conforme tipo de usuário)
    # ------------------------------------------------------------
    is_staff = school_user.is_staff_role

    if is_staff:
        subjects = (
            course.subjects.all()
            .prefetch_related(
                Prefetch(
                    "lessons",
                    queryset=Lesson.objects.all().order_by("order"),
                    to_attr="ordered_lessons"
                )
            )
            .order_by("order", "title")
        )
        lessons_qs = Lesson.objects.filter(subjects__course=course)

    else:
        subjects = (
            course.subjects.filter(status="published")
            .prefetch_related(
                Prefetch(
                    "lessons",
                    queryset=Lesson.objects.filter(status="published").order_by("order"),
                    to_attr="ordered_lessons"
                )
            )
            .order_by("order", "title")
        )
        lessons_qs = Lesson.objects.filter(subjects__course=course, status="published")


    # ------------------------------------------------------------
    # 3. Gate de matrícula para estudantes
    # ------------------------------------------------------------
    if school_user.role == "student":
        if not Enrollment.objects.filter(course=course, student=school_user).exists():
            messages.warning(request, "Você precisa se inscrever neste curso para acessá-lo.")
            return redirect("course_catalog", slug=slug)

    # ------------------------------------------------------------
    # 4. Totais e duração formatada
    # ------------------------------------------------------------
    total_subjects = subjects.count()

    # DISTINCT evita duplicatas do ManyToMany
    total_lessons = lessons_qs.distinct().count()

    duration = get_course_duration(course, published_only=not is_staff)
    total_duration_display = duration["formatted"]

    # ------------------------------------------------------------
    # 5. Progresso do usuário no curso
    # ------------------------------------------------------------
    course_progress = calculate_course_progress(school_user, course)

    # ------------------------------------------------------------
    # 6. Progressos de todos os alunos (para Professor/Admin)
    # ------------------------------------------------------------
    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("student__user")
    )

    if is_staff:
        students_progress = [
            {
                "student": e.student,
                "progress": round(
                    Progress.objects.filter(course=course, student=e.student)
                    .aggregate(avg=Avg("progress_percentage"))["avg"] or 0,
                    1
                )
            }
            for e in enrollments
        ]
    else:
        students_progress = None
    # ------------------------------------------------------------
    # Avaliações
    # ------------------------------------------------------------
    assessments = Assessment.objects.filter(course=course)
    
    # ------------------------------------------------------------
    # 7. Dados analíticos (para painel do curso)
    # ------------------------------------------------------------
    analytics_data = {
        "students": enrollments.count(),
        "total_subjects": total_subjects,
        "total_lessons": total_lessons,
        "total_duration": total_duration_display,
        "progress": round(course.average_progress, 1),
        "rating": round(course.average_rating or 0, 2),
        "views": course.views_count,
        "price": course.price,
        "is_free": course.is_free,
        "created_at": course.created_at,
        "published_at": course.published_at,
    }

    # ------------------------------------------------------------
    # 8. Contexto final
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "subjects": subjects,
        "assessments": assessments,
        "enrollments": enrollments,
        "students_progress": students_progress,
        "analytics_data": analytics_data,
        "course_progress": course_progress,

        # Totais (usados no template)
        "total_subjects": total_subjects,
        "total_lessons": total_lessons,
        "total_duration": total_duration_display,
    }

    # ------------------------------------------------------------
    # 9. Render com suporte a tema
    # ------------------------------------------------------------
    return t(request, school, "course/course_detail", context)


# ============================================================
# MEUS CURSOS (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def course_my_list(request, slug, school_user, school):

    base_qs = Course.objects.filter(school=school).select_related("category")

    # ============================================================
    # QUAIS CURSOS MOSTRAR?
    # ============================================================
    # Cursos em que o usuário está matriculado
    enrolled_ids = list(
        Enrollment.objects.filter(student=school_user, course__school=school)
        .values_list("course_id", flat=True)
    )
    total_enrolled = Enrollment.objects.filter(
        student=school_user, status="active", course__school=school
        ).count()

    match school_user.role:
        case "student":
            courses = (
                base_qs.filter(enrollments__student=school_user, status="active")
                .select_related("instructor")
                .prefetch_related("subjects", "subjects__lessons")
                .annotate(
                    total_lessons=Count("subjects__lessons", distinct=True),
                    total_minutes=Sum("subjects__lessons__duration")
                )
                .distinct()
            )
        case "teacher":
            courses = (
                base_qs.filter(instructor=request.user)
                .prefetch_related("subjects")
                .annotate(
                    total_lessons=Count("subjects__lessons", distinct=True),
                    total_minutes=Sum("subjects__lessons__duration")
                )
            )
        case _:
            courses = (
                base_qs
                .prefetch_related("subjects")
                .annotate(
                    total_lessons=Count("subjects__lessons", distinct=True),
                    total_minutes=Sum("subjects__lessons__duration")
                )
            )


    status_counts = base_qs.aggregate(
        active=Count("id", filter=Q(status="active")),
        draft=Count("id", filter=Q(status="draft")),
        archived=Count("id", filter=Q(status="archived")),
    )

    # ============================================================
    # 📌 PROGRESSO PESSOAL — AGORA FUNCIONA PARA QUALQUER USER
    # ============================================================
    user_course_progress = {}
    user_subject_progress = {}

    total_lessons = 0
    total_minutes = 0
    completed_lessons = 0
    completed_minutes = 0
    user_global_progress = 0

    if courses.exists():

        lessons_qs = (
            Lesson.objects.filter(
                subjects__course__in=courses,
                status="published"
            ).distinct()
        )

        total_lessons = lessons_qs.count()
        total_minutes = lessons_qs.aggregate(total=Sum("duration"))["total"] or 0

        # 🔥 agora admin/teacher também tem progresso
        progress_qs = Progress.objects.filter(
            student=school_user,
            course__in=courses,
            lesson__status="published",
        )

        # progresso global
        user_global_progress = (
            progress_qs.aggregate(avg=Avg("progress_percentage"))["avg"] or 0
        )


        completed_lessons = progress_qs.filter(is_completed=True).count()

        completed_minutes = (
            progress_qs.filter(is_completed=True)
            .aggregate(total=Sum("lesson__duration"))["total"] or 0
        )

        # ===== progresso por curso =====
        for course in courses:
            user_course_progress[course.id] = calculate_user_course_progress(school_user, course)

            # ===== progresso por matéria =====
            for subject in course.subjects.all():
                subj_progress = (
                    progress_qs.filter(
                        course=course,
                        lesson__subjects=subject,
                        lesson__status="published",
                    )
                    .aggregate(avg=Avg("progress_percentage"))["avg"]
                    or 0
                )
                user_subject_progress[subject.id] = round(subj_progress, 1)
        # progresso global real (média entre cursos)
        if user_course_progress:
            user_global_progress = sum(user_course_progress.values()) / len(user_course_progress)
        else:
            user_global_progress = 0

    # converter minutos → horas
    total_hours = round(total_minutes / 60, 1)
    completed_hours = round(completed_minutes / 60, 1)


    # ============================================================
    # DURAÇÃO / AULAS PUBLICADAS POR CURSO
    # ============================================================
    for c in courses:
        # Pega somente aulas publicadas do curso
        info = get_course_duration(c, published_only=True)
        c.total_duration_display = info["formatted"]
        c.published_minutes = info["minutes"]
        c.published_lessons_count = info["lessons"]


    # ============================================================
    # 📌 Contar cursos concluídos
    # ============================================================
    completed_courses_count = sum(
        1 for c in courses
        if user_course_progress.get(c.id, 0) == 100
    )

    # ============================================================
    # 🎬 Horas Assistidas (somente aulas completadas)
    # ============================================================
    # Horas assistidas em formato bonito
    hours = completed_minutes // 60
    minutes = completed_minutes % 60

    if hours > 0:
        total_hours_watched = f"{hours}h {minutes}min"
    else:
        total_hours_watched = f"{minutes}min"

    context = {
        "school": school,
        "school_user": school_user,
        "courses": courses,
        "completed_courses_count": completed_courses_count,
        "active_courses_count": status_counts["active"],
        "draft_courses_count": status_counts["draft"],
        "archived_courses_count": status_counts["archived"],
        "total_hours_watched": total_hours_watched,
        "enrolled_ids":enrolled_ids,

        # 📊 PROGRESSO PESSOAL (agora para qualquer tipo de usuário)
        "user_global_progress": round(user_global_progress, 1),
        "user_course_progress": user_course_progress,
        "user_subject_progress": user_subject_progress,
        "total_lessons": total_lessons,
        "completed_lessons": completed_lessons,
        "total_hours": total_hours,
        "completed_hours": completed_hours,
        "total_enrolled": total_enrolled,
    }

    return t(request, school, "course/course_my_list", context)


# ============================================================
# CRIAR CURSO (ADMINISTRATIVO)  —  VERSÃO OTIMIZADA
# ============================================================
@login_required
@school_context_required
@admin_required
def course_create(request, slug, school_user, school):
    """
    Criação de novo curso (somente administradores).
    View simplificada e otimizada.
    """

    categories = Category.objects.order_by("name")

    # ----------------------------------------
    # POST — salvar novo curso
    # ----------------------------------------
    if request.method == "POST":
        data = request.POST

        # Campos obrigatórios
        required_fields = ["title", "description", "category"]
        missing = [f for f in required_fields if not data.get(f)]

        if missing:
            messages.error(request, "Preencha todos os campos obrigatórios.")
            return redirect("course_create", slug=slug)

        # Normalização com fallback automático
        def to_int(value, default=None):
            try:
                return int(value)
            except:
                return default

        def to_float(value, default=0.0):
            try:
                return float(value)
            except:
                return default

        # Criar curso
        course = Course.objects.create(
            school=school,
            instructor=request.user,
            category_id=data.get("category"),

            # Campos de texto
            title=data.get("title").strip(),
            short_description=data.get("short_description", "").strip(),
            description=data.get("description", "").strip(),
            objectives=data.get("objectives", "").strip(),
            requirements=data.get("requirements", "").strip(),

            # Configurações
            level=data.get("level", "beginner"),
            status=data.get("status", "draft"),
            duration_hours=to_int(data.get("duration_hours"), 0),
            price=to_float(data.get("price"), 0.00),
            max_students=to_int(data.get("max_students"), None),
            video_intro=data.get("video_intro", "").strip(),

            # Booleanos
            certificate_available=("certificate_available" in data),
            is_featured=("is_featured" in data),
        )

        # Thumbnail
        thumbnail = request.FILES.get("thumbnail")
        if thumbnail:
            course.thumbnail = thumbnail
            course.save(update_fields=["thumbnail"])

        messages.success(request, f'Curso "{course.title}" criado com sucesso!')
        return redirect("course_detail", slug=slug, course_id=course.id)

    # ----------------------------------------
    # GET — mostrar formulário
    # ----------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "categories": categories,
    }

    return t(request, school, "course/course_create", context)


# ============================================================
# EDITAR CURSO (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def course_edit(request, slug, course_id, school_user, school):
    """Edição de curso existente (somente administradores)"""

    course = get_object_or_404(
        Course.objects.select_related("category", "instructor"),
        id=course_id,
        school=school
    )
    categories = Category.objects.order_by('name')

    # Permissão extra: instrutor pode editar o próprio curso
    if school_user.role != "admin" and course.instructor != request.user:
        messages.error(request, "Você não tem permissão para editar este curso.")
        return redirect("course_list", slug=slug)

    if request.method == "POST":
        # Campos simples
        fields_map = {
            "title": "title",
            "short_description": "short_description",
            "description": "description",
            "objectives": "objectives",
            "requirements": "requirements",
            "video_intro": "video_intro",
            "level": "level",
            "status": "status",
        }

        for form_key, model_field in fields_map.items():
            setattr(course, model_field, request.POST.get(form_key, getattr(course, model_field)))

        # Categoria
        category_id = request.POST.get("category")
        if category_id:
            course.category_id = category_id

        # Valores numéricos
        try:
            course.duration_hours = int(request.POST.get("duration_hours") or 0)
        except ValueError:
            course.duration_hours = 0

        try:
            course.price = float(request.POST.get("price") or 0.00)
        except ValueError:
            course.price = 0.00

        # Checkboxes
        course.certificate_available = request.POST.get("certificate_available") == "on"
        course.is_featured = request.POST.get("is_featured") == "on"

        # Thumbnail
        thumbnail = request.FILES.get("thumbnail")
        if thumbnail:
            course.thumbnail = thumbnail

        course.save()

        messages.success(request, f'Curso "{course.title}" atualizado com sucesso!')
        return redirect("course_list", slug=slug)

    # GET → renderizar formulário
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "categories": categories,
    }

    return t(request, school, "course/course_edit", context)


# ============================================================
# EXCLUIR CURSO (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def course_delete(request, slug, course_id, school_user, school):
    """
    Exclui um curso SOMENTE se não houver alunos matriculados.
    Professores e admins podem acessar a página, mas o delete só ocorre 
    quando o curso não possui matrículas ativas.
    """

    # Carrega o curso
    course = get_object_or_404(
        Course.objects.select_related("instructor"),
        id=course_id,
        school=school,
    )

    # Permissão: instrutor do curso ou admin
    if course.instructor != request.user and school_user.role != "admin":
        messages.error(request, "Você não tem permissão para excluir este curso.")
        return redirect("course_list", slug=slug)

    # ❗ Regra principal: SÓ DELETAR se não houver matrículas
    if course.enrollments.exists():
        messages.error(
            request,
            "Este curso não pode ser excluído pois possui alunos matriculados."
        )
        return redirect("course_list", slug=slug)

    # POST → excluir
    if request.method == "POST":
        title = course.title
        course.delete()
        messages.success(request, f'Curso "{title}" excluído com sucesso!')
        return redirect("course_list", slug=slug)

    # GET → página de confirmação
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "has_students": course.enrollments.exists(),
    }

    return t(request, school, "course/course_confirm_delete", context)


# ============================================================
# DUPLICAR CURSO (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def course_duplicate(request, slug, course_id, school_user, school):
    """
    Duplica apenas o curso (configurações),
    SEM copiar matérias, aulas ou avaliações.
    """
    original = get_object_or_404(Course, id=course_id, school=school)

    if original.instructor != request.user and school_user.role != 'admin':
        messages.error(request, 'Você não tem permissão para duplicar este curso.')
        return redirect('course_list', slug=slug)

    try:
        # cria o novo curso
        new_course = Course.objects.create(
            school=school,
            title=f"{original.title} (Cópia)",
            short_description=original.short_description,
            description=original.description,
            objectives=original.objectives,
            requirements=original.requirements,
            category=original.category,
            instructor=request.user,
            status='draft',              # sempre vira rascunho
            level=original.level,
            duration_hours=original.duration_hours,
            price=original.price,
            certificate_available=original.certificate_available,
            is_featured=original.is_featured,
            video_intro=original.video_intro,
            max_students=original.max_students,
        )

        # copia a thumbnail se existir
        if original.thumbnail:
            new_course.thumbnail = original.thumbnail
            new_course.save(update_fields=['thumbnail'])

        messages.success(request, f'Curso "{original.title}" duplicado, agora personalize-o!')
        return redirect('course_list', slug=slug, course_id=new_course.id)

    except Exception as e:
        messages.error(request, f'Erro ao duplicar curso: {str(e)}')
        return redirect('course_list', slug=slug)


# ============================================================
# ANALYTICS DO CURSO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def course_analytics(request, slug, school_user, school, course_id):
    """
    Página de estatísticas gerais do curso:
    - Total de alunos
    - Progresso médio da turma
    - Taxa de conclusão
    - Materiais totais
    - Tempo total de conteúdo
    - Aula mais assistida
    """

    # ------------------------------------------------------------
    # PERMISSÃO
    # ------------------------------------------------------------
    if school_user.role not in ["admin", "teacher"]:
        messages.error(request, "Você não tem permissão para acessar as análises deste curso.")
        return redirect("course_detail", slug=slug, course_id=course_id)

    # ------------------------------------------------------------
    # CURSO
    # ------------------------------------------------------------
    course = get_object_or_404(
        Course.objects.select_related("category", "instructor"),
        id=course_id,
        school=school
    )

    # ------------------------------------------------------------
    # ALUNOS MATRICULADOS
    # ------------------------------------------------------------
    enrollments = course.enrollments.select_related("student", "student__user")
    total_students = enrollments.count()

    # ------------------------------------------------------------
    # PROGRESSO MÉDIO DA TURMA
    # ------------------------------------------------------------
    avg_progress = (
        course.student_progress.aggregate(avg=Avg("progress_percentage"))["avg"] or 0
    )
    avg_progress = round(avg_progress, 1)

    # ------------------------------------------------------------
    # TAXA DE CONCLUSÃO
    # ------------------------------------------------------------
    completed_students = enrollments.filter(status="completed").count()

    completion_rate = (
        round((completed_students / total_students) * 100, 1)
        if total_students else 0
    )

    # ------------------------------------------------------------
    # MATERIAIS DO CURSO
    # ------------------------------------------------------------
    subjects = course.subjects.all()
    lessons_qs = Lesson.objects.filter(subjects__course=course).distinct()

    total_subjects = subjects.count()
    total_lessons = lessons_qs.count()

    # ------------------------------------------------------------
    # TEMPO TOTAL DE CONTEÚDO
    # ------------------------------------------------------------
    total_minutes = lessons_qs.aggregate(total=Sum("duration"))["total"] or 0
    h, m = divmod(total_minutes, 60)
    total_duration_display = f"{h}h {m}min" if h else f"{m}min"

    # ------------------------------------------------------------
    # AULA MAIS ASSISTIDA
    # ------------------------------------------------------------
    most_viewed_lesson = (
        Progress.objects
        .filter(course=course, is_completed=True)
        .values("lesson__title")
        .annotate(total=Count("lesson"))
        .order_by("-total")
        .first()
    )

    # ------------------------------------------------------------
    # CONTEXTO FINAL
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,

        "total_students": total_students,
        "avg_progress": avg_progress,
        "completion_rate": completion_rate,

        "total_subjects": total_subjects,
        "total_lessons": total_lessons,
        "total_duration": total_duration_display,

        "most_viewed_lesson": most_viewed_lesson,
    }

    return t(request, school, "course/course_analytics", context)


# ============================================================
# CATÁLOGO DE CURSOS  (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def school_courses(request, slug, school_user, school):
    """
    Catálogo de cursos (para alunos navegarem e se inscreverem)
    Inclui:
    - filtros
    - busca
    - ordenação
    - estatísticas gerais
    - paginação
    """

    # ------------------------------------------------------------
    # 1. QUERY BASE OTIMIZADA
    # ------------------------------------------------------------
    courses = (
        Course.objects.filter(status="active", school=school)
        .select_related("instructor", "category")
        .prefetch_related(
            "subjects",
            "subjects__lessons",
            "reviews",
            "enrollments__student__user",
        )
        .annotate(
            enrolled_count=Count("enrollments", distinct=True),
            lessons_count=Count("subjects__lessons", distinct=True),
            reviews_count=Count("reviews", distinct=True),
        )
    )

    # Cursos em que o usuário está matriculado
    enrolled_ids = list(
        Enrollment.objects.filter(student=school_user, course__school=school)
        .values_list("course_id", flat=True)
    )

    # ------------------------------------------------------------
    # 2. FILTROS
    # ------------------------------------------------------------

    # Categoria
    selected_category = request.GET.get("category")
    selected_category_name = None
    if selected_category:
        courses = courses.filter(category__slug=selected_category)
        selected_category_name = Category.objects.filter(slug=selected_category).values_list("name", flat=True).first()

    # Nível
    levels = request.GET.getlist("level")
    if levels:
        courses = courses.filter(level__in=levels)

    # Preço
    prices = request.GET.getlist("price")
    if prices:
        if prices == ["free"]:
            courses = courses.filter(price=0)
        elif prices == ["paid"]:
            courses = courses.filter(price__gt=0)

    # Duração em horas
    durations = request.GET.getlist("duration")
    if durations:
        q = Q()
        if "short" in durations:
            q |= Q(duration_hours__lte=2)
        if "medium" in durations:
            q |= Q(duration_hours__gt=2, duration_hours__lte=6)
        if "long" in durations:
            q |= Q(duration_hours__gt=6)
        courses = courses.filter(q)

    # Avaliação
    ratings = request.GET.getlist("rating")
    if ratings:
        min_rating = min(float(x) for x in ratings)
        courses = courses.filter(average_rating__gte=min_rating)

    # Recursos adicionais
    if "certificate" in request.GET.getlist("features"):
        courses = courses.filter(certificate_available=True)

    # Busca textual
    search_query = request.GET.get("search", "")
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(short_description__icontains=search_query)
        )

    # ------------------------------------------------------------
    # 3. ORDENAÇÃO
    # ------------------------------------------------------------
    sort_by = request.GET.get("sort", "popular")

    ordering_map = {
        "recent": "-created_at",
        "rating": ["-average_rating", "-reviews_count"],
        "price-low": "price",
        "price-high": "-price",
        "popular": ["-enrolled_count", "-views_count"],
    }

    courses = courses.order_by(
        *ordering_map.get(sort_by, ["-enrolled_count", "-views_count"])
        if isinstance(ordering_map.get(sort_by), list)
        else ordering_map.get(sort_by)
    )

    # ------------------------------------------------------------
    # 4. ESTATÍSTICAS GERAIS
    # ------------------------------------------------------------
    all_active = Course.objects.filter(status="active", school=school)

    categories = (
        Category.objects.annotate(
            courses_count=Count("courses", filter=Q(courses__status="active", courses__school=school))
        )
        .filter(courses_count__gt=0)
    )

    stats = {
        "beginner": all_active.filter(level="beginner").count(),
        "intermediate": all_active.filter(level="intermediate").count(),
        "advanced": all_active.filter(level="advanced").count(),
        "free": all_active.filter(price=0).count(),
        "paid": all_active.filter(price__gt=0).count(),
        "total_courses": all_active.count(),
        "total_students": Enrollment.objects.filter(course__school=school).count(),
        "total_instructors": User.objects.filter(
            courses_taught__school=school,
            courses_taught__status="active"
        ).distinct().count(),
        "total_hours": all_active.aggregate(total=Sum("duration_hours"))["total"] or 0,
    }

    # ------------------------------------------------------------
    # 5. PAGINAÇÃO
    # ------------------------------------------------------------
    page_number = request.GET.get("page", 1)
    paginator = Paginator(courses, 12)
    courses_page = paginator.get_page(page_number)

    # ------------------------------------------------------------
    # 6. CONTEXTO FINAL
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,

        "courses": courses_page,
        "categories": categories,

        "selected_category": selected_category,
        "selected_category_name": selected_category_name,

        "search_query": search_query,
        "current_sort": sort_by,

        "enrolled_ids": enrolled_ids,
        **stats,
    }

    return t(request, school, "course/course_catalog", context)



# ============================================================
# INSCRIÇÃO EM CURSO (ALUNO / PROFESSOR / ADMIN)
# ============================================================
@login_required
@school_context_required
def enroll_in_course(request, slug, course_id, school_user, school):
    """Realiza a matrícula do usuário em um curso ativo, respeitando limites e regras."""

    # ------------------------------------------------------------
    # 1. Busca curso e valida disponibilidade
    # ------------------------------------------------------------
    course = get_object_or_404(
        Course.objects.select_related("instructor", "category"),
        id=course_id,
        school=school
    )

    if course.status != "active":
        messages.error(request, "❌ Este curso não está disponível no momento.")
        return redirect("course_catalog", slug=slug)

    # ------------------------------------------------------------
    # 2. Verifica limite de vagas
    # ------------------------------------------------------------
    if course.max_students and course.enrollments.count() >= course.max_students:
        messages.warning(request, "⚠️ O limite de alunos deste curso foi atingido.")
        return redirect("course_detail", slug=slug, course_id=course.id)

    # ------------------------------------------------------------
    # 3. Cria matrícula (ou identifica se já existe)
    # ------------------------------------------------------------
    enrollment, created = Enrollment.objects.get_or_create(
        course=course,
        student=school_user,
        defaults={"status": "in_progress"}
    )

    # ------------------------------------------------------------
    # 4. Feedback visual
    # ------------------------------------------------------------
    if created:
        messages.success(
            request,
            f"🎉 Inscrição realizada com sucesso em “{course.title}”!"
        )
    else:
        messages.info(request, "ℹ️ Você já está matriculado neste curso.")

    # ------------------------------------------------------------
    # 5. Redireciona para a página do curso
    # ------------------------------------------------------------
    return redirect("course_detail", slug=slug, course_id=course.id)


# ============================================================
# CRIAR CATEGORY (ADMINISTRATIVO)
# ============================================================
@school_context_required
@admin_required
@login_required
def category_create(request, slug, school_user, school):
    """
    Cria uma nova categoria via formulário.
    Apenas administradores podem criar categorias.
    """

    # ------------------------------------------------------------
    # 1. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == 'POST':

        # 1.1 Coletar dados do formulário
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        icon = request.POST.get('icon', '').strip()
        color = request.POST.get('color', '#667eea')

        # ------------------------------------------------------------
        # 1.2 Validações básicas
        # ------------------------------------------------------------
        if not name:
            messages.error(request, 'O nome da categoria é obrigatório.')
            return redirect('course_create', slug=slug)

        if Category.objects.filter(name__iexact=name).exists():
            messages.warning(request, f'A categoria "{name}" já existe.')
            return redirect('course_create', slug=slug)

        # ------------------------------------------------------------
        # 1.3 Criar categoria
        # ------------------------------------------------------------
        Category.objects.create(
            name=name,
            description=description,
            icon=icon,
            color=color
        )

        messages.success(request, f'Categoria "{name}" criada com sucesso!')
        return redirect('course_create', slug=slug)

    # ------------------------------------------------------------
    # 2. Redirecionar caso acesso via GET
    # ------------------------------------------------------------
    return redirect('course_create', slug=slug)


# ============================================================
# LISTAR CATEGORIAS (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def category_list(request, slug, school_user, school):
    """
    Lista todas as categorias disponíveis.
    Apenas administradores podem acessar.
    """

    # ------------------------------------------------------------
    # 1. Buscar categorias da escola
    # ------------------------------------------------------------
    categories = Category.objects.annotate(
        courses_count=Count('courses', filter=Q(courses__school=school))
    ).order_by('name')

    # ------------------------------------------------------------
    # 2. Contexto para template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'categories': categories,
    }

    # ------------------------------------------------------------
    # 3. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, 'category_list', context)


# ============================================================
# EDITAR CATEGORIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def category_edit(request, slug, category_id, school_user, school):
    """
    Edita uma categoria existente (somente administradores)
    """

    # ------------------------------------------------------------
    # 1. Buscar categoria pelo ID
    # ------------------------------------------------------------
    category = get_object_or_404(Category, id=category_id)

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == 'POST':
        category.name = request.POST.get('name', category.name).strip()
        category.description = request.POST.get('description', '').strip()
        category.icon = request.POST.get('icon', '').strip()
        category.color = request.POST.get('color', category.color)

        if request.FILES.get('image'):
            category.image = request.FILES['image']

        category.save()

        # ------------------------------------------------------------
        # 3. Mensagem de sucesso e redirecionamento
        # ------------------------------------------------------------
        messages.success(request, f'Categoria "{category.name}" atualizada com sucesso!')
        return redirect('category_list', slug=slug)

    # ------------------------------------------------------------
    # 4. Contexto para template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'category': category,
    }

    # ------------------------------------------------------------
    # 5. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, 'category_edit', context)


# ============================================================
# EXCLUIR CATEGORIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def category_delete(request, slug, category_id, school_user, school):
    """
    Deleta uma categoria (somente administradores)
    """

    # ------------------------------------------------------------
    # 1. Buscar categoria pelo ID
    # ------------------------------------------------------------
    category = get_object_or_404(Category, id=category_id)

    # ------------------------------------------------------------
    # 2. Contar cursos vinculados à categoria na escola atual
    # ------------------------------------------------------------
    courses_count = category.courses.filter(school=school).count()

    # ------------------------------------------------------------
    # 3. Processar POST (tentativa de exclusão)
    # ------------------------------------------------------------
    if request.method == 'POST':
        if courses_count > 0:
            messages.warning(
                request,
                f'Não é possível excluir "{category.name}" pois existem {courses_count} curso(s) vinculados.'
            )
        else:
            name = category.name
            category.delete()
            messages.success(request, f'Categoria "{name}" excluída com sucesso!')

        return redirect('category_list', slug=slug)

    # ------------------------------------------------------------
    # 4. Contexto para template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'category': category,
        'courses_count': courses_count,
    }

    # ------------------------------------------------------------
    # 5. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, 'category_delete', context)

