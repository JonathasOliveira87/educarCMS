from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST

from .helpers import themed_template
from .decorators import school_context_required, admin_required


# ============================================================
# PÁGINA DE CONFIGURAÇÕES DA ESCOLA
# ============================================================
@login_required
@school_context_required
@admin_required
def school_settings(request, slug, school_user, school):

    # ------------------------------------------------------------
    # Renderiza a página de configurações gerais da escola
    # ------------------------------------------------------------
    return render(request, themed_template(school, 'school_settings'), {
        'school': school,
        'school_user': school_user,
    })


# ============================================================
# ATUALIZA OS DADOS DA ESCOLA
# ============================================================
@login_required
@school_context_required
@admin_required
@require_POST
def school_settings_update(request, slug, school_user, school):

    # ------------------------------------------------------------
    # Campos simples mapeados: form_field → model_field
    # ------------------------------------------------------------
    fields = {
        "name": "school_name",
        "slogan": "slogan",
        "email": "contact_email",
        "telephone": "phone",
        "badge": "badge",
    }

    # ------------------------------------------------------------
    # Atualiza campos básicos (nome, email, telefone etc)
    # ------------------------------------------------------------
    for model_field, form_field in fields.items():
        value = request.POST.get(form_field)
        if value is not None:
            setattr(school, model_field, value)

    # ------------------------------------------------------------
    # Upload do logo (arquivo)
    # ------------------------------------------------------------
    if request.FILES.get("logo"):
        school.logo = request.FILES["logo"]

    # ------------------------------------------------------------
    # Validação mínima antes de salvar
    # ------------------------------------------------------------
    if not school.name.strip():
        messages.error(request, "O nome da escola não pode ficar vazio.")

    else:
        school.save()
        messages.success(request, "Perfil da escola atualizado com sucesso!")

    # ------------------------------------------------------------
    # Redireciona de volta à página de configurações
    # ------------------------------------------------------------
    return redirect('school_settings', slug=slug)
