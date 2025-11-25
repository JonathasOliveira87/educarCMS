from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.shortcuts import redirect
from .models import Course, Assessment, Attempt, Answer, Question, Choice, Enrollment, SchoolUser
from .decorators import school_context_required, teacher_required, admin_required
from django.db.models import Avg
from django.contrib import messages
from .helpers import t


# ============================================================
# DETALHE DA AVALIAÇÃO (ALUNO)
# ============================================================
@login_required
@school_context_required
def assessment_detail(request, slug, assessment_id, school_user, school):
    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Verificar matrícula do aluno no curso
    # ------------------------------------------------------------
    is_enrolled = Enrollment.objects.filter(
        course=assessment.course,
        student=school_user
    ).exists()

    # ------------------------------------------------------------
    # 3. Buscar tentativas (somente para alunos)
    # ------------------------------------------------------------
    attempts = None
    if school_user.role == 'student':
        attempts = Attempt.objects.filter(
            assessment=assessment,
            student=school_user
        ).order_by('-started_at')

    # ------------------------------------------------------------
    # 4. Contexto para template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'assessment': assessment,
        'is_enrolled': is_enrolled,
        'attempts': attempts,
    }
    # ------------------------------------------------------------
    # 5. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/detail", context)


# ============================================================
# INICIAR AVALIAÇÃO (ALUNO)
# ============================================================
@login_required
@school_context_required
@transaction.atomic
def assessment_start(request, slug, assessment_id, school_user, school):

    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Garantir que apenas alunos possam iniciar tentativas
    # ------------------------------------------------------------
    if school_user.role != 'student':
        return redirect('assessment_detail', slug=school.slug, assessment_id=assessment.id)

    # ------------------------------------------------------------
    # 3. Verificar matrícula no curso
    # ------------------------------------------------------------
    is_enrolled = Enrollment.objects.filter(
        course=assessment.course,
        student=school_user
    ).exists()

    if not is_enrolled:
        return redirect('assessment_detail', slug=school.slug, assessment_id=assessment.id)

    # ------------------------------------------------------------
    # 4. Respeitar limite de tentativas permitidas
    # ------------------------------------------------------------
    existing_attempts = Attempt.objects.filter(
        assessment=assessment,
        student=school_user
    ).count()

    if existing_attempts >= assessment.attempts_allowed:
        return redirect('assessment_detail', slug=school.slug, assessment_id=assessment.id)

    # ------------------------------------------------------------
    # 5. Verificar janela de abertura e fechamento
    # ------------------------------------------------------------
    now = timezone.now()

    if assessment.open_at and now < assessment.open_at:
        return redirect('assessment_detail', slug=school.slug, assessment_id=assessment.id)

    if assessment.close_at and now > assessment.close_at:
        return redirect('assessment_detail', slug=school.slug, assessment_id=assessment.id)

    # ------------------------------------------------------------
    # 6. Criar nova tentativa
    # ------------------------------------------------------------
    attempt_number = existing_attempts + 1

    attempt = Attempt.objects.create(
        student=school_user,
        assessment=assessment,
        attempt_number=attempt_number
    )

    # ------------------------------------------------------------
    # 7. Redirecionar para a realização da avaliação
    # ------------------------------------------------------------
    return redirect(
        'assessment_take',
        slug=school.slug,
        assessment_id=assessment.id,
        attempt_id=attempt.id
    )


# ============================================================
# FINALIZAR TENTATIVA (HELPER)
# ============================================================
def _finalize_attempt_and_redirect(request, school, attempt, auto_submit=False):
    """
    Finaliza a tentativa e redireciona para a página de resultado.
    Por enquanto, se não tiver nota calculada ainda, joga 0.
    """

    # ------------------------------------------------------------
    # 1. Se a tentativa ainda não foi submetida, marcar como submetida
    # ------------------------------------------------------------
    if not attempt.is_submitted:
        attempt.is_submitted = True

        # ------------------------------------------------------------
        # 2. Registrar data/hora de finalização
        # ------------------------------------------------------------
        attempt.finished_at = timezone.now()

        # ------------------------------------------------------------
        # 3. Caso ainda não exista nota calculada, atribuir 0
        # ------------------------------------------------------------
        if attempt.score is None:
            attempt.score = 0

        # ------------------------------------------------------------
        # 4. Salvar a tentativa no banco
        # ------------------------------------------------------------
        attempt.save()

    # ------------------------------------------------------------
    # 5. Redirecionar para a página de resultado dessa tentativa
    # ------------------------------------------------------------
    return redirect(
        'assessment_result',
        slug=school.slug,
        assessment_id=attempt.assessment.id,
        attempt_id=attempt.id
    )


# ============================================================
# REALIZAR AVALIAÇÃO (ALUNO)
# ============================================================
@login_required
@school_context_required
@transaction.atomic
def assessment_take(request, slug, assessment_id, attempt_id, school_user, school):

    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Buscar tentativa do aluno
    # ------------------------------------------------------------
    attempt = get_object_or_404(
        Attempt,
        id=attempt_id,
        assessment=assessment,
        student=school_user
    )

    # ------------------------------------------------------------
    # 3. Buscar questões da avaliação
    # ------------------------------------------------------------
    questions = assessment.questions.all().order_by('order')

    # ------------------------------------------------------------
    # 4. Bloquear caso a tentativa já tenha sido enviada
    # ------------------------------------------------------------
    if attempt.is_submitted:
        return redirect(
            'assessment_result',
            slug=school.slug,
            assessment_id=assessment.id,
            attempt_id=attempt.id
        )

    # ------------------------------------------------------------
    # 5. Verificar tempo limite (se existir)
    # ------------------------------------------------------------
    if assessment.time_limit:
        elapsed = (timezone.now() - attempt.started_at).total_seconds() / 60
        if elapsed > assessment.time_limit:
            return _finalize_attempt_and_redirect(
                request, school, attempt, auto_submit=True
            )

    # ------------------------------------------------------------
    # 6. Processar respostas (POST)
    # ------------------------------------------------------------
    if request.method == 'POST':

        total_points = 0
        score_obtained = 0

        for question in questions:
            field_name = f"question_{question.id}"
            value = request.POST.get(field_name)

            total_points += float(question.points)

            # Criar ou atualizar resposta
            answer, created = Answer.objects.get_or_create(
                attempt=attempt,
                question=question,
            )

            # --------------------------------------------------------
            # 6.1 Questões de múltipla escolha / verdadeiro-falso
            # --------------------------------------------------------
            if question.type in ['multiple_choice', 'true_false']:
                if value:
                    try:
                        choice = Choice.objects.get(id=value, question=question)
                        answer.choice = choice
                        answer.is_correct = choice.is_correct
                        answer.text_answer = ""
                        answer.file_answer = None
                        answer.save()

                        if choice.is_correct:
                            score_obtained += float(question.points)

                    except Choice.DoesNotExist:
                        pass

            # --------------------------------------------------------
            # 6.2 Questões dissertativas
            # --------------------------------------------------------
            elif question.type == 'essay':
                answer.text_answer = value or ""
                answer.choice = None
                answer.is_correct = False  # correção manual posterior
                answer.save()

            # --------------------------------------------------------
            # 6.3 Questões com upload de arquivo
            # --------------------------------------------------------
            elif question.type == 'file':
                uploaded_file = request.FILES.get(field_name)
                if uploaded_file:
                    answer.file_answer = uploaded_file
                answer.choice = None
                answer.is_correct = False
                answer.save()

        # ------------------------------------------------------------
        # 7. Finalizar e salvar nota
        # ------------------------------------------------------------
        attempt.is_submitted = True
        attempt.finished_at = timezone.now()
        attempt.score = round(score_obtained, 2) if total_points > 0 else 0
        attempt.save()

        return redirect(
            'assessment_result',
            slug=school.slug,
            assessment_id=assessment.id,
            attempt_id=attempt.id
        )

    # ------------------------------------------------------------
    # 8. Renderizar template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'assessment': assessment,
        'attempt': attempt,
        'questions': questions,
    }

    return t(request, school, "assessments/take", context)


    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    attempt = get_object_or_404(
        Attempt,
        id=attempt_id,
        assessment=assessment,
        student=school_user
    )

    answers = attempt.answers.select_related('question', 'choice')

    # calcula % de acertos em questões objetivas
    objective_questions = assessment.questions.filter(type__in=['multiple_choice', 'true_false'])
    total_obj = objective_questions.count()
    correct_obj = answers.filter(question__in=objective_questions, is_correct=True).count()
    percent_correct = (correct_obj / total_obj * 100) if total_obj > 0 else 0

    context = {
        'school': school,
        'school_user': school_user,
        'assessment': assessment,
        'attempt': attempt,
        'answers': answers,
        'percent_correct': percent_correct,
    }
    return t(request, school, "assessments/result", context)


# ============================================================
# RESULTADO DA AVALIAÇÃO
# ============================================================
@login_required
@school_context_required
def assessment_result(request, slug, assessment_id, attempt_id, school_user, school):
    """
    Exibe o resultado da tentativa do aluno, incluindo percentual de acertos.
    """

    # ------------------------------------------------------------
    # 1. Buscar avaliação da escola
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Buscar tentativa do próprio aluno
    # ------------------------------------------------------------
    attempt = get_object_or_404(
        Attempt,
        id=attempt_id,
        assessment=assessment,
        student=school_user
    )

    # ------------------------------------------------------------
    # 3. Puxar respostas com dados relacionados
    # ------------------------------------------------------------
    answers = attempt.answers.select_related('question', 'choice')

    # ------------------------------------------------------------
    # 4. Calcular % de acertos em questões objetivas
    # ------------------------------------------------------------
    objective_questions = assessment.questions.filter(
        type__in=['multiple_choice', 'true_false']
    )
    total_obj = objective_questions.count()
    correct_obj = answers.filter(
        question__in=objective_questions,
        is_correct=True
    ).count()
    percent_correct = (correct_obj / total_obj * 100) if total_obj > 0 else 0

    # ------------------------------------------------------------
    # 5. Montar contexto para o template
    # ------------------------------------------------------------
    context = {
        'school': school,
        'school_user': school_user,
        'assessment': assessment,
        'attempt': attempt,
        'answers': answers,
        'percent_correct': percent_correct,
    }

    # ------------------------------------------------------------
    # 6. Renderizar página de resultado
    # ------------------------------------------------------------
    return t(request, school, "assessments/result", context)


# ============================================================
# LISTAR AVALIAÇÕES DO CURSO
# ============================================================
@login_required
@school_context_required
@teacher_required
def assessment_list(request, slug, course_id, school_user, school):
    """
    Exibe todas as avaliações associadas ao curso.
    Permissão já controlada pelos decoradores.
    """

    # ------------------------------------------------------------
    # 1. Buscar o curso pertencente à escola
    # ------------------------------------------------------------
    course = get_object_or_404(
        Course,
        id=course_id,
        school=school
    )

    # ------------------------------------------------------------
    # 2. Buscar todas as avaliações do curso
    # ------------------------------------------------------------
    assessments = course.assessments.all().order_by("-created_at")

    # ------------------------------------------------------------
    # 3. Avaliações sem matéria (subject=None)
    # ------------------------------------------------------------
    course_assessments = assessments.filter(subject__isnull=True)

    # ------------------------------------------------------------
    # 4. Agrupar avaliações por matéria
    # ------------------------------------------------------------
    subjects_with_assessments = {}
    for a in assessments.filter(subject__isnull=False):
        subject = a.subject
        if subject not in subjects_with_assessments:
            subjects_with_assessments[subject] = []
        subjects_with_assessments[subject].append(a)

    # ------------------------------------------------------------
    # 5. Construir contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "course_assessments": course_assessments,
        "subjects_with_assessments": subjects_with_assessments,
    }

    # ------------------------------------------------------------
    # 6. Renderizar página
    # ------------------------------------------------------------
    return t(request, school, "assessments/assessment_list", context)


# ============================================================
# CRIAR AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required 
def assessment_create(request, slug, course_id, school_user, school):
    """
    Página para criação de nova avaliação dentro de um curso.
    Permissões já garantidas pelos decoradores.
    """

    # ------------------------------------------------------------
    # 1. Buscar o curso e suas matérias
    # ------------------------------------------------------------
    course = get_object_or_404(
        Course,
        id=course_id,
        school=school
    )
    subjects = course.subjects.all()

    # ------------------------------------------------------------
    # 2. Se for POST, processar criação da avaliação
    # ------------------------------------------------------------
    if request.method == "POST":

        # Campos principais
        title = request.POST["title"]
        description = request.POST.get("description", "")
        type = request.POST.get("type", "quiz")
        subject_id = request.POST.get("subject")

        # --------------------------------------------------------
        # 2.1 Conversões de tipos para salvar corretamente
        # --------------------------------------------------------
        weight_raw = request.POST.get("weight")
        weight = float(weight_raw) if weight_raw not in (None, "") else 0

        attempts_raw = request.POST.get("attempts_allowed")
        attempts = int(attempts_raw) if attempts_raw not in (None, "") else 1

        time_limit_raw = request.POST.get("time_limit")
        time_limit = int(time_limit_raw) if time_limit_raw not in (None, "") else None

        open_at = request.POST.get("open_at") or None
        close_at = request.POST.get("close_at") or None

        # Matéria vinculada
        subject = None
        if subject_id:
            subject = subjects.filter(id=subject_id).first()

        # --------------------------------------------------------
        # 2.2 Criar a avaliação
        # --------------------------------------------------------
        Assessment.objects.create(
            course=course,
            subject=subject,
            title=title,
            description=description,
            type=type,
            weight=weight,
            attempts_allowed=attempts,
            time_limit=time_limit,
            open_at=open_at,
            close_at=close_at,
        )

        # --------------------------------------------------------
        # 2.3 Redirecionar após criar
        # --------------------------------------------------------
        return redirect("assessment_list", slug=school.slug, course_id=course.id)
    
    # ------------------------------------------------------------
    # 3. Contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "course": course,
        "subjects": subjects,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/assessment_create", context)


# ============================================================
# EDITAR AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def assessment_edit(request, slug, assessment_id, school_user, school):
    """
    Página para edição de avaliação existente.
    Permissões já garantidas pelos decoradores.
    """

    # ------------------------------------------------------------
    # 1. Buscar a avaliação e suas matérias relacionadas
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )
    subjects = assessment.course.subjects.all()

    # ------------------------------------------------------------
    # 2. Se for POST, processar atualização
    # ------------------------------------------------------------
    if request.method == "POST":
        try:
            # Campos principais
            assessment.title = request.POST["title"]
            assessment.description = request.POST.get("description", "")
            assessment.type = request.POST.get("type", "quiz")

            # --------------------------------------------------------
            # 2.1 Conversões de tipos
            # --------------------------------------------------------

            # Peso
            weight_raw = request.POST.get("weight")
            assessment.weight = float(weight_raw) if weight_raw not in (None, "") else 0

            # Tentativas permitidas
            attempts_raw = request.POST.get("attempts_allowed")
            assessment.attempts_allowed = int(attempts_raw) if attempts_raw not in (None, "") else 1

            # Tempo limite
            time_limit_raw = request.POST.get("time_limit")
            assessment.time_limit = int(time_limit_raw) if time_limit_raw not in (None, "") else None

            # Datas
            assessment.open_at = request.POST.get("open_at") or None
            assessment.close_at = request.POST.get("close_at") or None

            # Salvar
            assessment.save()

            # --------------------------------------------------------
            # 2.2 Mensagem de sucesso e redirecionamento
            # --------------------------------------------------------
            messages.success(request, "Avaliação atualizada com sucesso!")

            return redirect(
                "assessment_list",
                slug=school.slug,
                course_id=assessment.course.id
            )

        except Exception as e:
            # --------------------------------------------------------
            # 2.3 Mensagem de erro
            # --------------------------------------------------------
            messages.error(request, f"Erro ao salvar a avaliação: {e}")

    # ------------------------------------------------------------
    # 3. Contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "assessment": assessment,
        "subjects": subjects,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/assessment_edit", context)


# ============================================================
# EXCLUIR AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def assessment_delete(request, slug, assessment_id, school_user, school):
    """
    Exclui uma avaliação inteira, incluindo suas questões.
    """

    # ------------------------------------------------------------
    # 1. Buscar a avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )
    course_id = assessment.course.id
    title = assessment.title

    # ------------------------------------------------------------
    # 2. Excluir a avaliação
    # ------------------------------------------------------------
    assessment.delete()

    # ------------------------------------------------------------
    # 3. Mensagem de confirmação
    # ------------------------------------------------------------
    messages.success(request, f"A avaliação **{title}** foi excluída com sucesso!")

    # ------------------------------------------------------------
    # 4. Redirecionar para lista
    # ------------------------------------------------------------
    return redirect(
        "assessment_list",
        slug=school.slug,
        course_id=course_id
    )


# ============================================================
# LISTAR QUESTÕES DA AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def question_list(request, slug, assessment_id, school_user, school):
    """
    Mostra todas as questões cadastradas na avaliação.
    """

    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Buscar questões da avaliação ordenadas
    # ------------------------------------------------------------
    questions = assessment.questions.all().order_by("order")

    # ------------------------------------------------------------
    # 3. Contexto
    # ------------------------------------------------------------
    context= {
        "school": school,
        "school_user": school_user,
        "assessment": assessment,
        "questions": questions,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/question_list", context)


# ============================================================
# CRIAR QUESTÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def question_create(request, slug, assessment_id, school_user, school):
    """
    Criar uma nova questão para a avaliação.
    Pode ser múltipla escolha, dissertativa, verdadeiro/falso, envio de arquivo.
    """

    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == "POST":
        Question.objects.create(
            assessment=assessment,
            text=request.POST["text"],
            type=request.POST["type"],
            order=request.POST.get("order", 1),
            points=request.POST.get("points", 1),
        )

        return redirect(
            "question_list",
            slug=school.slug,
            assessment_id=assessment.id
        )

    # ------------------------------------------------------------
    # 3. Contexto
    # ------------------------------------------------------------
    context= {
        "school": school,
        "school_user": school_user,
        "assessment": assessment,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/question_create", context)


# ============================================================
# EDITAR QUESTÃO DA AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def question_edit(request, slug, question_id, school_user, school):
    """
    Edita texto, tipo, ordem e pontos de uma questão específica.
    A edição só ocorre se a questão pertence à escola atual.
    """

    # --------------------------------------------
    # Buscar questão vinculada à escola
    # --------------------------------------------
    question = get_object_or_404(
        Question,
        id=question_id,
        assessment__course__school=school
    )

    # --------------------------------------------
    # Processar envio do formulário
    # --------------------------------------------
    if request.method == "POST":

        # Texto da questão
        question.text = request.POST.get("text", "").strip()

        # Tipo da questão (ex: 'multi', 'boolean', etc.)
        question.type = request.POST.get("type", question.type)

        # Ordem da questão (com fallback seguro)
        try:
            question.order = int(request.POST.get("order", question.order))
        except ValueError:
            pass  # mantém o valor atual se vier errado

        # Pontos da questão
        try:
            question.points = float(request.POST.get("points", question.points))
        except ValueError:
            pass

        # Salvar alterações
        question.save()

        # --------------------------------------------
        # Redirecionar de volta à lista de questões
        # --------------------------------------------
        return redirect(
            "question_list",
            slug=school.slug,
            assessment_id=question.assessment.id
        )

    # --------------------------------------------
    # Renderizar formulário de edição
    # --------------------------------------------
    return render(request, "themes/NeoLearn/assessments/question_edit.html", {
        "school": school,
        "school_user": school_user,
        "question": question,
    })


# ============================================================
# EXCLUIR QUESTÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def question_delete(request, slug, question_id, school_user, school):
    """
    Exclui a questão selecionada.
    """

    # ------------------------------------------------------------
    # 1. Buscar questão
    # ------------------------------------------------------------
    question = get_object_or_404(
        Question,
        id=question_id,
        assessment__course__school=school
    )

    # ------------------------------------------------------------
    # 2. Guardar ID da avaliação antes de excluir
    # ------------------------------------------------------------
    assessment_id = question.assessment.id

    # ------------------------------------------------------------
    # 3. Excluir questão
    # ------------------------------------------------------------
    question.delete()

    # ------------------------------------------------------------
    # 4. Redirecionar
    # ------------------------------------------------------------
    return redirect(
        "question_list",
        slug=school.slug,
        assessment_id=assessment_id
    )


# ============================================================
# LISTAR ALTERNATIVAS DA QUESTÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def choice_list(request, slug, question_id, school_user, school):
    """
    Lista todas as alternativas de uma questão de múltipla escolha.
    """

    # ------------------------------------------------------------
    # 1. Buscar questão
    # ------------------------------------------------------------
    question = get_object_or_404(
        Question,
        id=question_id,
        assessment__course__school=school
    )

    # ------------------------------------------------------------
    # 2. Buscar alternativas
    # ------------------------------------------------------------
    choices = question.choices.all().order_by("order")

    # ------------------------------------------------------------
    # 3. Contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "question": question,
        "choices": choices,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/choice_list", context)


# ============================================================
# CRIAR NOVA ALTERNATIVA (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def choice_create(request, slug, question_id, school_user, school):
    """
    Cria uma nova alternativa para uma questão.
    """

    # ------------------------------------------------------------
    # 1. Buscar questão
    # ------------------------------------------------------------
    question = get_object_or_404(
        Question,
        id=question_id,
        assessment__course__school=school
    )

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == "POST":
        # (a) Criar alternativa
        Choice.objects.create(
            question=question,
            text=request.POST["text"],
            is_correct="is_correct" in request.POST,
            order=request.POST.get("order", 1)
        )

        # (b) Redirecionar
        return redirect(
            "choice_list",
            slug=school.slug,
            question_id=question.id
        )

    # ------------------------------------------------------------
    # 3. Contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "question": question,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/choice_create", context)


# ============================================================
# EDITAR ALTERNATIVA DA QUESTÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def choice_edit(request, slug, choice_id, school_user, school):
    """
    Edita texto, ordem e marca se a alternativa é correta.
    """

    # ------------------------------------------------------------
    # 1. Buscar alternativa
    # ------------------------------------------------------------
    choice = get_object_or_404(
        Choice,
        id=choice_id,
        question__assessment__course__school=school
    )

    # ------------------------------------------------------------
    # 2. Processar envio do formulário
    # ------------------------------------------------------------
    if request.method == "POST":
        # (a) Atualizar campos
        choice.text = request.POST["text"]
        choice.order = request.POST["order"]
        choice.is_correct = "is_correct" in request.POST

        # (b) Salvar
        choice.save()

        # (c) Redirecionar
        return redirect(
            "choice_list",
            slug=school.slug,
            question_id=choice.question.id
        )

    # ------------------------------------------------------------
    # 3. Contexto para template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "choice": choice,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/choice_edit", context)


# ============================================================
# EXCLUIR ALTERNATIVA DA QUESTÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def choice_delete(request, slug, choice_id, school_user, school):
    """
    Remove alternativa e redireciona de volta à lista.
    """

    # ------------------------------------------------------------
    # 1. Buscar alternativa
    # ------------------------------------------------------------
    choice = get_object_or_404(
        Choice,
        id=choice_id,
        question__assessment__course__school=school
    )

    # ------------------------------------------------------------
    # 2. Guardar ID da questão para redirecionamento
    # ------------------------------------------------------------
    question_id = choice.question.id

    # ------------------------------------------------------------
    # 3. Apagar alternativa
    # ------------------------------------------------------------
    choice.delete()

    # ------------------------------------------------------------
    # 4. Redirecionar para lista de alternativas
    # ------------------------------------------------------------
    return redirect(
        "choice_list",
        slug=school.slug,
        question_id=question_id
    )


# ============================================================
# LISTA DE SUBMISSÕES DA AVALIAÇÃO (ADMIN / PROFESSOR)
# ============================================================
@login_required
@school_context_required
@teacher_required
def assessment_submissions(request, slug, assessment_id, school_user, school):
    """
    Mostra todas as tentativas realizadas pelos alunos.
    """

    # ------------------------------------------------------------
    # 1. Buscar avaliação
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )

    # ------------------------------------------------------------
    # 2. Carregar tentativas dos alunos
    # ------------------------------------------------------------
    attempts = (
        assessment.attempts
        .select_related("student")
        .order_by("-started_at")
    )

    # ------------------------------------------------------------
    # 3. Montar contexto
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "assessment": assessment,
        "attempts": attempts,
    }

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    return t(request, school, "assessments/submission_list", context)


# ============================================================
# CORRIGIR TENTATIVA DO ALUNO (PROFESSOR)
# ============================================================
@login_required
@school_context_required
def grade_attempt(request, slug, assessment_id, attempt_id, school_user, school):
    """
    Professor corrige questões dissertativas e por upload.
    Recalcula a nota final considerando questões objetivas e manuais.
    """

    # ------------------------------------------------------------
    # 1. Buscar tentativa e respostas
    # ------------------------------------------------------------
    attempt = get_object_or_404(
        Attempt,
        id=attempt_id,
        assessment_id=assessment_id,
        assessment__course__school=school
    )

    answers = attempt.answers.select_related("question")

    # ------------------------------------------------------------
    # 2. Processar correção e recalcular nota (POST)
    # ------------------------------------------------------------
    if request.method == "POST":

        total_score = 0

        for answer in answers:
            question_points = float(answer.question.points)

            # 2.1 Questões objetivas (já corrigidas)
            if answer.question.type in ["multiple_choice", "true_false"]:
                if answer.is_correct:
                    total_score += question_points

            # 2.2 Questões com correção manual
            elif answer.question.type in ["essay", "file"]:
                grade_field = f"grade_{answer.id}"
                grade_value = request.POST.get(grade_field)

                if grade_value:
                    total_score += float(grade_value)

        # ------------------------------------------------------------
        # 3. Atualizar tentativa com nota final
        # ------------------------------------------------------------
        attempt.score = round(total_score, 2)
        attempt.is_submitted = True
        attempt.save()

        return redirect(
            "assessment_submissions",
            slug=school.slug,
            assessment_id=assessment_id
        )

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "attempt": attempt,
        "answers": answers,
    }

    return t(request, school, "assessments/grade_attempt", context)


# ============================================================
# ESTATÍSTICAS DA AVALIAÇÃO (ALUNO)
# Média, acertos por questão, questão mais difícil, desempenho
# ============================================================
@login_required
@school_context_required
def assessment_stats(request, slug, assessment_id, school_user, school):
    """
    Mostra estatísticas gerais e detalhadas da avaliação.
    """

    # ------------------------------------------------------------
    # 1. Buscar avaliação e tentativas enviadas
    # ------------------------------------------------------------
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
        course__school=school
    )
    attempts = assessment.attempts.filter(is_submitted=True)

    # ------------------------------------------------------------
    # 2. Processar estatísticas globais
    # ------------------------------------------------------------
    total = attempts.count()
    avg_score = attempts.aggregate(avg=Avg("score"))["avg"] or 0

    # ------------------------------------------------------------
    # 3. Estatísticas por questão
    # ------------------------------------------------------------
    difficult_questions = []

    for q in assessment.questions.all():

        # Total de respostas
        total_ans = Answer.objects.filter(question=q).count()

        # Total de acertos
        correct_ans = Answer.objects.filter(
            question=q,
            is_correct=True
        ).count()

        # Taxa de acerto (%)
        correct_rate = (correct_ans / total_ans * 100) if total_ans else 0

        difficult_questions.append({
            "question": q,
            "correct_rate": round(correct_rate, 2),
        })

    # Ordenar da mais difícil (menor acerto) para a mais fácil
    difficult_questions = sorted(
        difficult_questions,
        key=lambda x: x["correct_rate"]
    )

    # ------------------------------------------------------------
    # 4. Renderizar template
    # ------------------------------------------------------------
    context = {
        "school": school,
        "school_user": school_user,
        "assessment": assessment,
        "attempts": attempts,
        "total": total,
        "avg_score": round(avg_score, 2),
        "difficult_questions": difficult_questions,
    }

    return t(request, school, "assessments/assessment_stats", context)

