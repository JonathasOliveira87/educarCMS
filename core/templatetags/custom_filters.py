from django import template
from ..views import calculate_subject_progress


register = template.Library()



@register.filter
def to(value, end):
    """Retorna um range de value até end (inclusivo)."""
    return range(int(value), int(end) + 1)

@register.filter
def div(value, arg):
    """Divide dois números."""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0

@register.filter
def mul(value, arg):
    """Multiplica dois números."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def format_duration(value):
    """
    Converte minutos decimais (ex: 0.591) para formato mm:ss.
    """
    try:
        total_seconds = float(value) * 60
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        return f"{minutes}:{seconds:02d}"
    except Exception:
        return "0:00"
    

@register.filter
def get_subject_progress(subject, student):
    return calculate_subject_progress(student, subject)


from core.models import Progress  # adicione se ainda não importou


@register.filter
def get_lesson_completed(lesson, student):
    """Retorna True se o aluno concluiu a lição."""
    return Progress.objects.filter(
        student=student,
        lesson=lesson,
        is_completed=True
    ).exists()


@register.filter
def dict_get(dictionary, key):
    """Retorna dictionary[key] com segurança."""
    try:
        return dictionary.get(key, 0)
    except Exception:
        return 0
    
@register.filter
def youtube_embed(url):
    """Converte URL do YouTube para formato embed"""
    if not url:
        return ''
    
    video_id = None
    
    # Para URLs do tipo youtu.be
    if 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[-1].split('?')[0]
    
    # Para URLs do tipo youtube.com/watch?v=
    elif 'watch?v=' in url:
        video_id = url.split('watch?v=')[-1].split('&')[0]
    
    # Se encontrou o ID, retorna o embed
    if video_id:
        return f'https://www.youtube-nocookie.com/embed/{video_id}'
    
    return url