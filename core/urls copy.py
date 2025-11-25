from django.shortcuts import redirect
from django.urls import path
from . import views, assessments_views, courses_views, lessons_views

urlpatterns = [
    # -----------------------------
    # PORTAL PÚBLICO
    # -----------------------------
    path('', views.portal_home, name='portal_home'),

    # -----------------------------
    # Catálogo público
    # -----------------------------


    # -----------------------------
    # AUTENTICAÇÃO LOGIN / LOGOUT
    # -----------------------------
    path("login/", lambda request: redirect("/")),
    path('school/<slug:slug>/', views.auth_login_or_dashboard, name='auth_login'),
    path('school/<slug:slug>/logout/', views.auth_logout, name='auth_logout'),

    # -----------------------------
    # DASHBOARD
    # -----------------------------
    path('school/<slug:slug>/dashboard/', views.school_dashboard, name='school_dashboard'),

    # -----------------------------
    # CONFIGURAÇÕES
    # -----------------------------
    path('school/<slug:slug>/settings/', views.school_settings, name='school_settings'),
    path('school/<slug:slug>/settings/update/', views.school_settings_update, name='school_settings_update'),
    path('school/<slug:slug>/appearance/update/', views.school_appearance_update, name='school_appearance_update'),

    # -----------------------------
    # PAINEL ADMINISTRATIVO
    # -----------------------------
    path('school/<slug:slug>/admin/', views.school_admin_panel, name='school_admin_panel'),

    # -----------------------------
    # CATEGORIAS DE CURSOS
    # -----------------------------
    path('school/<slug:slug>/category/', courses_views.category_list, name='category_list'),
    path('school/<slug:slug>/category/create/', courses_views.category_create, name='category_create'),
    path('school/<slug:slug>/category/<int:category_id>/update/', courses_views.category_edit, name='category_edit'),
    path('school/<slug:slug>/category/<int:category_id>/delete/', courses_views.category_delete, name='category_delete'),

    # -----------------------------
    # CURSOS
    # -----------------------------
    path('school/<slug:slug>/courses/views/', courses_views.course_list, name='course_list'),
    path('school/<slug:slug>/courses/<int:course_id>/detail/', courses_views.course_detail, name='course_detail'),
    path('school/<slug:slug>/courses/my/', courses_views.course_my_list, name='course_my_list'),
    path('school/<slug:slug>/courses/catalog/', courses_views.school_courses, name='course_catalog'),
    path('school/<slug:slug>/courses/create/', courses_views.course_create, name='course_create'),
    path('school/<slug:slug>/courses/<int:course_id>/update/', courses_views.course_edit, name='course_edit'),
    path('school/<slug:slug>/courses/<int:course_id>/delete/', courses_views.course_delete, name='course_delete'),
    path('school/<slug:slug>/courses/<int:course_id>/duplicate/', courses_views.course_duplicate, name='course_duplicate'),
    path('school/<slug:slug>/courses/<int:course_id>/analytics/', courses_views.course_analytics, name='course_analytics'),
    path('school/<slug:slug>/courses/<int:course_id>/enroll/', courses_views.enroll_in_course, name='enroll_in_course'),

    # -----------------------------
    # MÓDULOS
    # -----------------------------
    path('school/<slug:slug>/courses/<int:course_id>/subject/create/', views.subject_create, name='subject_create'),
    path('school/<slug:slug>/courses/<int:course_id>/subject/<int:subject_id>/update/', views.subject_update, name='subject_update'),
    path('school/<slug:slug>/courses/<int:course_id>/subject/<int:subject_id>/delete/', views.subject_delete, name='subject_delete'),
    
    # -----------------------------
    # AULAS
    # -----------------------------
    path('school/<slug:slug>/courses/<int:course_id>/subject/<int:subject_id>/lesson/create/', lessons_views.lesson_create, name='lesson_create'),
    path('school/<slug:slug>/courses/<int:course_id>/subject/<int:subject_id>/lesson/<int:lesson_id>/update/', lessons_views.lesson_update, name='lesson_update'),
    path('school/<slug:slug>/courses/<int:course_id>/subject/<int:subject_id>/lesson/<int:lesson_id>/delete/', lessons_views.lesson_delete, name='lesson_delete'),# remove vínculo apenas
    path('school/<slug:slug>/courses/<int:course_id>/lesson/<int:lesson_id>/delete/permanent/', lessons_views.lesson_delete_permanent, name='lesson_delete_permanent'),# deleta de fato 
    path("school/<slug:slug>/courses/<int:course_id>/lessons/<int:lesson_id>/progress/", lessons_views.lesson_progress_update, name="lesson_progress_update"),
    path('school/<slug:slug>/courses/<int:course_id>/lessons/<int:lesson_id>/', lessons_views.lesson_view,name='lesson_view'),

    # -----------------------------
    # Avaliações
    # -----------------------------
    path("school/<slug:slug>/course/<int:course_id>/assessments/", assessments_views.assessment_list, name="assessment_list"),
    path("school/<slug:slug>/course/<int:course_id>/assessments/create/", assessments_views.assessment_create,name="assessment_create"),
    path("school/<slug:slug>/assessments/<int:assessment_id>/edit/", assessments_views.assessment_edit, name="assessment_edit"),
    path("school/<slug:slug>/assessments/<int:assessment_id>/delete/", assessments_views.assessment_delete, name="assessment_delete"),
    path("school/<slug:slug>/assessments/<int:assessment_id>/questions/", assessments_views.question_list, name="question_list"),
    path("school/<slug:slug>/assessments/<int:assessment_id>/questions/create/", assessments_views.question_create, name="question_create"),
    path("school/<slug:slug>/questions/<int:question_id>/edit/", assessments_views.question_edit, name="question_edit"),  # Editar questão
    path("school/<slug:slug>/questions/<int:question_id>/delete/", assessments_views.question_delete, name="question_delete"),  # Excluir questão
    path("school/<slug:slug>/questions/<int:question_id>/choices/", assessments_views.choice_list, name="choice_list"),  # Listar alternativas (múltipla escolha)
    path("school/<slug:slug>/questions/<int:question_id>/choices/create/", assessments_views.choice_create, name="choice_create"),  # Criar alternativa
    path("school/<slug:slug>/choices/<int:choice_id>/edit/", assessments_views.choice_edit, name="choice_edit"),  # Editar alternativa
    path("school/<slug:slug>/choices/<int:choice_id>/delete/", assessments_views.choice_delete, name="choice_delete"),  # Excluir alternativa
    path("school/<slug:slug>/assessments/<int:assessment_id>/submissions/", assessments_views.assessment_submissions, name="assessment_submissions"),  # Listar tentativas de um assessment
    path("school/<slug:slug>/assessments/<int:assessment_id>/attempt/<int:attempt_id>/grade/", assessments_views.grade_attempt, name="grade_attempt"),  # Corrigir tentativa específica
    path("school/<slug:slug>/assessments/<int:assessment_id>/stats/", assessments_views.assessment_stats, name="assessment_stats"),  # Estatísticas de um assessment
    path('school/<slug:slug>/assessments/<int:assessment_id>/', assessments_views.assessment_detail, name='assessment_detail'),
    path('school/<slug:slug>/assessments/<int:assessment_id>/start/', assessments_views.assessment_start, name='assessment_start'),
    path('school/<slug:slug>/assessments/<int:assessment_id>/attempt/<int:attempt_id>/', assessments_views.assessment_take, name='assessment_take'),
    path('school/<slug:slug>/assessments/<int:assessment_id>/attempt/<int:attempt_id>/result/', assessments_views.assessment_result, name='assessment_result'),

    # -----------------------------
    # PERFIL
    # -----------------------------
    path('school/<slug:slug>/perfil/', views.profile, name='profile'),
    path('school/<slug:slug>/perfil/update/', views.profile_update, name='profile_update'),
    path('school/<slug:slug>/perfil/preferences/', views.profile_preferences, name='profile_preferences'),
    path('school/<slug:slug>/perfil/notifications/', views.profile_notifications, name='profile_notifications'),
    path('school/<slug:slug>/perfil/upload/', views.profile_avatar_upload, name='profile_avatar_upload'),
    path('school/<slug:slug>/perfil/banner/', views.profile_banner_upload, name='profile_banner_upload'),
    path('school/<slug:slug>/perfil/password/', views.change_password, name='change_password'),

    # -----------------------------
    # USUÁRIOS 
    # -----------------------------
    path('school/<slug:slug>/users/', views.manage_users, name='manage_users'),
    path('school/<slug:slug>/users/create/', views.create_user, name='create_user'),
    path('school/<slug:slug>/users/<int:user_id>/update/', views.edit_user, name='edit_user'),
    path('school/<slug:slug>/users/<int:user_id>/delete/', views.delete_user, name='delete_user'),

]
