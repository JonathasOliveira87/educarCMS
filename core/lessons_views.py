from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from .models import Subject, Course, Lesson, LessonVideo, Enrollment, Progress
from .helpers import t, estimate_duration, update_course_duration, mark_lesson_as_completed
from .decorators import school_context_required, admin_required
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .views import calculate_course_progress
import json

User = get_user_model()

from decimal import Decimal

# ============================================================
# CRIAR AULA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def lesson_create(request, slug, course_id, subject_id, school_user, school):
    # ------------------------------------------------------------
    # 1. Buscar curso e disciplina
    # ------------------------------------------------------------
    course = get_object_or_404(Course, id=course_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=course)

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        content_type = request.POST.get('content_type', 'video')
        duration = request.POST.get('duration', 0)
        status = request.POST.get('status', 'draft')
        order = int(request.POST.get('order', 1))

        # ------------------------------------------------------------
        # 2a. Validação do título
        # ------------------------------------------------------------
        if not title:
            messages.error(request, "O título da aula é obrigatório.")
            return redirect('course_detail', slug=slug, course_id=course.id)

        try:
            # ------------------------------------------------------------
            # 2b. Criar aula com dados básicos
            # ------------------------------------------------------------
            initial_duration = 0 if content_type == 'video' else estimate_duration(content_type, duration)

            lesson = Lesson.objects.create(
                school=school,
                title=title,
                description=description,
                content_type=content_type,
                duration=initial_duration,
                status=status,
                order=order,
            )

            subject.lessons.add(lesson)

            # ------------------------------------------------------------
            # 2c. Tipos de conteúdo específicos
            # ------------------------------------------------------------
            if content_type == 'text':
                lesson.content = request.POST.get('content_text', '').strip()
                lesson.save()

            elif content_type == 'file':
                uploaded_file = request.FILES.get('content_file')
                if uploaded_file:
                    fs = FileSystemStorage()
                    filename = fs.save(uploaded_file.name, uploaded_file)
                    lesson.file = filename
                    lesson.save()

            elif content_type == 'quiz':
                quiz_question = request.POST.get('quiz_question', '').strip()
                quiz_answers = request.POST.get('quiz_answers', '').strip()
                lesson.description = quiz_question
                lesson.content = quiz_answers
                lesson.save()

            elif content_type == 'video':
                video_title = request.POST.get('video_title', '').strip()
                video_file = request.FILES.get('video_file')
                video_duration = request.POST.get('video_duration')

                if not video_file:
                    messages.error(request, "Você precisa enviar um arquivo de vídeo.")
                    return redirect('course_detail', slug=slug, course_id=course.id)

                try:
                    duration_dec = Decimal(str(video_duration)) if video_duration else Decimal('0')
                except:
                    duration_dec = Decimal('0')

                video_instance = LessonVideo.objects.create(
                    lesson=lesson,
                    title=video_title if video_title else video_file.name,
                    file=video_file,
                    duration=duration_dec,
                    order=1,
                )

                lesson.duration = float(duration_dec)
                lesson.save()

            # ------------------------------------------------------------
            # 2d. Atualiza duração total do curso
            # ------------------------------------------------------------
            update_course_duration(course)

            messages.success(request, f'Aula "{lesson.title}" criada com sucesso!')
            return redirect('course_detail', slug=slug, course_id=course.id)

        except Exception as e:
            messages.error(request, f'Erro ao criar a aula: {str(e)}')
            return redirect('course_detail', slug=slug, course_id=course.id)

    # ------------------------------------------------------------
    # 3. Requisição inválida
    # ------------------------------------------------------------
    messages.warning(request, "Requisição inválida.")
    return redirect('course_detail', slug=slug, course_id=course.id)


# ============================================================
# ATUALIZAR AULA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def lesson_update(request, slug, course_id, subject_id, lesson_id, school_user, school):
    # ------------------------------------------------------------
    # 1. Buscar curso, disciplina e aula
    # ------------------------------------------------------------
    course = get_object_or_404(Course, id=course_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, school=school)
    videos = lesson.videos.all()

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        content_type = request.POST.get('content_type', 'video')
        status = request.POST.get('status', 'draft')
        order = int(request.POST.get('order', 1))

        # ------------------------------------------------------------
        # 2a. Validação do título
        # ------------------------------------------------------------
        if not title:
            messages.error(request, "O título da aula é obrigatório.")
            return redirect('course_detail', slug=slug, course_id=course.id)

        # ------------------------------------------------------------
        # 2b. Atualizar campos básicos da aula
        # ------------------------------------------------------------
        lesson.title = title
        lesson.description = description
        lesson.content_type = content_type
        lesson.status = status
        lesson.order = order

        # ------------------------------------------------------------
        # 2c. Tratamento por tipo de conteúdo
        # ------------------------------------------------------------
        if content_type == 'text':
            lesson.content = request.POST.get('content_text', lesson.content)

        elif content_type == 'file':
            uploaded_file = request.FILES.get('content_file')
            if uploaded_file:
                lesson.file = uploaded_file

        elif content_type == 'quiz':
            lesson.description = request.POST.get('quiz_question', lesson.description)
            lesson.content = request.POST.get('quiz_answers', lesson.content)

        elif content_type == 'video':
            existing_video = lesson.videos.first()
            video_title = request.POST.get('video_title', '').strip()
            video_file = request.FILES.get('video_file')
            video_duration = request.POST.get('video_duration')

            # --------------------------------------------------------
            # 2c-i. Novo arquivo enviado
            # --------------------------------------------------------
            if video_file:
                lesson.videos.all().delete()
                try:
                    duration_dec = Decimal(str(video_duration)) if video_duration else Decimal('0')
                except:
                    duration_dec = Decimal('0')

                LessonVideo.objects.create(
                    lesson=lesson,
                    title=video_title if video_title else video_file.name,
                    file=video_file,
                    duration=duration_dec,
                    order=1
                )
                lesson.duration = float(duration_dec)

            # --------------------------------------------------------
            # 2c-ii. Mantém vídeo existente
            # --------------------------------------------------------
            elif existing_video:
                existing_video.title = video_title if video_title else existing_video.title
                try:
                    duration_dec = Decimal(str(video_duration)) if video_duration else existing_video.duration
                except:
                    duration_dec = existing_video.duration
                existing_video.duration = duration_dec
                existing_video.save()
                lesson.duration = float(existing_video.duration)

            # --------------------------------------------------------
            # 2c-iii. Nenhum vídeo enviado
            # --------------------------------------------------------
            else:
                lesson.duration = 0

        # ------------------------------------------------------------
        # 2d. Salvar aula
        # ------------------------------------------------------------
        lesson.save()

        # ------------------------------------------------------------
        # 2e. Atualiza duração total do curso
        # ------------------------------------------------------------
        update_course_duration(course)

        messages.success(request, f'Aula "{lesson.title}" atualizada com sucesso!')
        return redirect('course_detail', slug=slug, course_id=course.id)

    # ------------------------------------------------------------
    # 3. GET → Renderizar template do modal com dados existentes
    # ------------------------------------------------------------
    context = {
        "lesson": lesson,
        "modal_id": "modalUpdateLesson",
        "course": course,
        "subject": subject,
        "video": videos.first() if videos.exists() else None
    }
    return t(request, school, "course/course_detail", context)


# ============================================================
# REMOVER AULA DA MATÉRIA (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def lesson_delete(request, slug, course_id, subject_id, lesson_id, school_user, school):
    """
    Remove a aula da matéria (sem deletar do banco).
    """
    course = get_object_or_404(Course, id=course_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, school=school)

    if request.method == 'POST':
        subject.lessons.remove(lesson)
        messages.success(
            request, f'Aula "{lesson.title}" removida da matéria "{subject.title}".'
        )
    else:
        messages.error(request, "A remoção deve ser feita via POST.")

    return redirect('course_detail', slug=slug, course_id=course.id)


# ============================================================
# EXCLUIR AULA PERMANENTEMENTE (ADMINISTRATIVO)
# ============================================================
@login_required
@school_context_required
@admin_required
def lesson_delete_permanent(request, slug, course_id, lesson_id, school_user, school):
    """
    Exclui uma aula definitivamente do banco (somente administradores).
    """
    course = get_object_or_404(Course, id=course_id, school=school)
    lesson = get_object_or_404(Lesson, id=lesson_id, school=school)

    if request.method == 'POST':
        title = lesson.title
        lesson.delete()
        messages.success(request, f'Aula "{title}" excluída permanentemente.')
    else:
        messages.error(request, "A exclusão deve ser feita via POST.")

    return redirect('course_detail', slug=slug, course_id=course.id)


# ============================================================
# AULA: VIEW UNIFICADA (vídeo, texto e quiz)
# ============================================================
@login_required
@school_context_required
def lesson_view(request, slug, course_id, lesson_id, school_user, school):
    import random
    from django.db.models import Prefetch, Sum, Avg

    # ======================================================
    # 🔍 1. Busca curso e aula
    # ======================================================
    course = get_object_or_404(Course, id=course_id, school=school)
    lesson = get_object_or_404(Lesson, id=lesson_id, school=school)

    # Bloqueia acesso se estiver em rascunho e o usuário não for staff
    if lesson.status != 'published' and not request.user.is_staff:
        return redirect('course_detail', slug=slug, course_id=course_id)

    # 🔒 Verifica matrícula se for aluno
    if school_user.role == "student" and not Enrollment.objects.filter(course=course, student=school_user).exists():
        messages.warning(request, "Você precisa estar matriculado neste curso para acessar esta aula.")
        return redirect('course_detail', slug=slug, course_id=course.id)

    # ✅ Marca como concluída
    mark_lesson_as_completed(school_user, course, lesson)

    # ======================================================
    # 📚 2. Módulo e aulas relacionadas
    # ======================================================
    subject = lesson.subjects.first()  # pega o módulo (matéria) principal
    lessons = Lesson.objects.filter(subjects=subject, status='published').order_by('order').distinct()

    # ======================================================
    # 🎯 3. Lista de matérias do curso (com aulas)
    # ======================================================
    if school_user.role in ['admin', 'teacher']:
        subjects = course.subjects.all().prefetch_related('lessons')
        lessons_qs = Lesson.objects.filter(subjects__course=course)
    else:
        subjects = course.subjects.filter(status='published').prefetch_related(
            Prefetch('lessons', queryset=Lesson.objects.filter(status='published'))
        )
        lessons_qs = Lesson.objects.filter(subjects__course=course, status='published')

    # ======================================================
    # 🧮 4. Cálculos de totais
    # ======================================================
    total_subjects = subjects.count()
    total_lessons = lessons_qs.distinct().count()
    total_duration_min = lessons_qs.aggregate(Sum('duration'))['duration__sum'] or 0

    # Converte minutos em horas e minutos legíveis
    hours = total_duration_min // 60
    minutes = total_duration_min % 60
    if hours and minutes:
        total_duration_display = f"{hours}h {minutes}min"
    elif hours:
        total_duration_display = f"{hours}h"
    else:
        total_duration_display = f"{minutes}min"

    # ======================================================
    # 🧾 4.1 Contagem por tipo de aula
    # ======================================================
    count_video = lessons_qs.filter(content_type='video').count()
    count_text = lessons_qs.filter(content_type='text').count()
    count_quiz = lessons_qs.filter(content_type='quiz').count()
    count_file = lessons_qs.filter(content_type='file').count()

    # ======================================================
    # 🧩 5. Quiz (caso a aula seja do tipo quiz)
    # ======================================================
    options, correct_answer = [], None
    if lesson.content_type == 'quiz':
        options = [opt.strip() for opt in (lesson.content or "").split(",") if opt.strip()]
        correct_answer = options[0] if options else None
        random.shuffle(options)

        if request.method == "POST":
            chosen = request.POST.get("answer")
            if chosen == correct_answer:
                messages.success(request, "✅ Resposta correta! Parabéns!")
            else:
                messages.error(request, f"❌ Resposta incorreta. A correta era: {correct_answer}")
            return redirect('lesson_view', slug=slug, course_id=course.id, lesson_id=lesson.id)

    # ======================================================
    # 📊 6. Progresso e estatísticas
    # ======================================================
    enrollments = Enrollment.objects.filter(course=course).select_related('student__user')
    students_progress = []
    for enrollment in enrollments:
        avg_progress = (
            Progress.objects.filter(course=course, student=enrollment.student)
            .aggregate(avg=Avg('progress_percentage'))['avg'] or 0
        )
        students_progress.append({
            'student': enrollment.student,
            'progress': round(avg_progress, 1),
        })

    # ======================================================
    # 📈 7. Progresso do aluno neste módulo
    # ======================================================
    total_lessons_in_subject = subject.lessons.filter(status='published').count() if subject else 0

    completed_lessons_in_subject = Progress.objects.filter(
        course=course,
        student=school_user,
        lesson__subjects=subject,
        is_completed=True
    ).distinct().count()


    if total_lessons_in_subject > 0:
        progress_in_subject = round((completed_lessons_in_subject / total_lessons_in_subject) * 100, 1)
    else:
        progress_in_subject = 0

    # ======================================================
    # 🎁 8. Contexto
    # ======================================================
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "lesson": lesson,
        "subject": subject,
        "subjects": subjects,
        "lessons": lessons,
        "options": options,
        "correct_answer": correct_answer,
        "students_progress": students_progress,
        "total_subjects": total_subjects,
        "total_lessons": total_lessons,
        "total_duration_display": total_duration_display,  # ✅ Soma do tempo de todas as aulas
        "progress": round(course.average_progress, 1), # Progresso Médio da Turma
        "count_video": count_video,
        "count_text": count_text,
        "count_quiz": count_quiz,
        "count_file": count_file,
        "completed_lessons_in_subject": completed_lessons_in_subject,
        "total_lessons_in_subject": total_lessons_in_subject,
        "progress_in_subject": progress_in_subject,
    }
    
    
    # Usa o mesmo template para todos os tipos
    return t(request, school, "lesson_unified", context)



@login_required
@school_context_required
@require_POST
def lesson_progress_update(request, slug, course_id, lesson_id, school_user, school):
    if request.method == "POST":
        course = get_object_or_404(Course, id=course_id, school=school)
        lesson = get_object_or_404(Lesson, id=lesson_id)

        data = json.loads(request.body)
        is_completed = data.get("is_completed", False)

        # Atualiza o progresso do aluno
        progress, created = Progress.objects.get_or_create(
            student=school_user,
            course=course,
            lesson=lesson,
            defaults={"is_completed": is_completed}
        )
        if not created:
            progress.is_completed = is_completed
            progress.save()

        # Calcula o progresso atualizado do curso
        new_progress = calculate_course_progress(school_user, course)

        return JsonResponse({
            "success": True,
            "is_completed": is_completed,
            "course_progress": round(new_progress, 1)
        })

    return JsonResponse({"success": False}, status=400)
