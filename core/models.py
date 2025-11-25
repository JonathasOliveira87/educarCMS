from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.utils.text import slugify
import os
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils.crypto import get_random_string
from django.db.models import Avg
import uuid
from django.utils import timezone


telefone_validator = RegexValidator(
    regex=r'^\(?\d{2}\)?\s?(?:9\d{4}|\d{4})-?\d{4}$',
    message="Digite um número de telefone válido no formato (XX) XXXXX-XXXX ou (XX) XXXX-XXXX.",
    code='invalid_phone'
)

def default_end_date():
    return date.today() + timedelta(days=30)

def school_logo_upload_path(instance, filename):
    # instance é o objeto School
    # slugify transforma o nome da escola em algo seguro para pastas
    name_slug = slugify(instance.name)
    ext = filename.split('.')[-1]  # mantém a extensão original
    # caminho: media/nomedaescola/logo.ext
    return os.path.join(name_slug, f"logo.{ext}")

# Escola
class School(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    theme = models.CharField(max_length=50, default='default')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="schools")
    email = models.EmailField(max_length=255, blank=True, null=True)
    telephone = models.CharField(max_length=15, validators=[telefone_validator], blank=True, null=True)
    logo = models.ImageField(upload_to=school_logo_upload_path, null=True, blank=True)
    badge = models.CharField(max_length=50, blank=True, null=True)
    slogan = models.CharField(max_length=255, blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#667eea")
    secondary_color = models.CharField(max_length=7, default="#764ba2")
    created_at = models.DateTimeField(auto_now_add=True)
    theme_mode = models.CharField(
        max_length=10,
        choices=[("light", "Claro"), ("dark", "Escuro"), ("auto", "Automático")],
        default="light"
    )
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# Usuários vinculados à escola
class SchoolUser(models.Model):
    ROLE_CHOICES = [('admin','Admin'),('teacher','Teacher'),('student','Student')]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
 
    phone = models.CharField(max_length=20, blank=True, null=True, validators=[telefone_validator])
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name="Criado em")
    
    class Meta:
        unique_together = ('user', 'school')

    @property
    def courses(self):
        """Retorna todos os cursos em que o usuário está matriculado."""
        return Course.objects.filter(enrollments__student=self) 
       
    @property
    def is_staff_role(self):
        return self.role in ("admin", "teacher")
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.role})"


# Assinaturas das escolas
class Subscription(models.Model):
    school = models.OneToOneField('School', on_delete=models.CASCADE)
    plan = models.CharField(max_length=50, choices=[('basic','Básico'),('pro','Profissional'),('premium','Premium')])
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(default=default_end_date)
    active = models.BooleanField(default=True)

    def is_active(self):
        today = date.today()
        return self.active and self.start_date <= today <= self.end_date



# ============================================================
#  CATEGORY
# ============================================================
class Category(models.Model):
    name = models.CharField('Nome', max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField('Descrição', blank=True)
    icon = models.CharField('Ícone', max_length=50, blank=True)
    color = models.CharField('Cor', max_length=20, blank=True, help_text="Ex: #667eea")
    image = models.ImageField('Imagem', upload_to='categories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{get_random_string(4)}"
            self.slug = slug
        super().save(*args, **kwargs)


# ============================================================
#  COURSE
# ============================================================
class Course(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Rascunho'),
        ('active', 'Ativo'),
        ('archived', 'Arquivado'),
    ]
    LEVEL_CHOICES = [
        ('beginner', 'Iniciante'),
        ('intermediate', 'Intermediário'),
        ('advanced', 'Avançado'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE)

    title = models.CharField('Título', max_length=50)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField('Descrição')
    short_description = models.CharField('Descrição Curta', max_length=100, blank=True)

    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses_taught', verbose_name='Instrutor')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name='Categoria')

    thumbnail = models.ImageField('Thumbnail', upload_to='courses/thumbnails/', blank=True, null=True)
    video_intro = models.URLField('Vídeo de Introdução', blank=True)

    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='draft')
    level = models.CharField('Nível', max_length=20, choices=LEVEL_CHOICES, default='beginner')
    duration_hours = models.PositiveIntegerField('Duração (horas)', default=0)
    price = models.DecimalField('Preço', max_digits=10, decimal_places=2, default=0.00)

    requirements = models.TextField('Requisitos', blank=True)
    objectives = models.TextField('Objetivos', blank=True)

    views_count = models.PositiveIntegerField('Visualizações', default=0)
    average_rating = models.DecimalField('Avaliação Média', max_digits=3, decimal_places=2, default=0.00)

    is_featured = models.BooleanField('Destaque', default=False)
    certificate_available = models.BooleanField('Certificado Disponível', default=True)
    max_students = models.PositiveIntegerField('Máximo de Alunos', null=True, blank=True)

    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    published_at = models.DateTimeField('Publicado em', null=True, blank=True)

    class Meta:
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            while Course.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{get_random_string(4)}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_free(self):
        return self.price == 0

    @property
    def students_count(self):
        return self.enrollments.count()

    @property
    def is_published(self):
        return self.status == 'active'

    @property #Progresso Médio da Turma
    def average_progress(self):
        progresses = self.student_progress.all()
        if not progresses.exists():
            return 0
        return progresses.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
    

# ============================================================
# SUBJECT
# ============================================================
class Subject(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='subjects')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Rascunho'),
            ('published', 'Publicado'),
        ],
        default='draft'
    )
    # 🔹 Relacionamento flexível: uma matéria pode ter várias aulas,
    # e uma aula pode pertencer a várias matérias.
    lessons = models.ManyToManyField('Lesson', related_name='subjects', blank=True)

    def __str__(self):
        return f"{self.title} ({self.course.title})"


# ============================================================
#  LESSON
# ============================================================
class Lesson(models.Model):
    school = models.ForeignKey('School', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content_type = models.CharField(max_length=20, choices=[
        ('video', 'Vídeo'),
        ('text', 'Texto'),
        ('file', 'Arquivo'),
        ('quiz', 'Quiz'),
    ], default='video')
    content = models.TextField(blank=True)
    video_url = models.URLField(blank=True, null=True)
    file = models.FileField(upload_to='lessons/files/', blank=True, null=True)  # ✅ novo campo
    duration = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField(default=1) 
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Rascunho'),
        ('published', 'Publicado'),
    ], default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    
# ============================================================
#  LESSON VIDEO (múltiplos vídeos por aula)
# ============================================================
class LessonVideo(models.Model):
    lesson = models.ForeignKey('Lesson', on_delete=models.CASCADE, related_name='videos')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='lessons/videos/')
    duration = models.DecimalField(max_digits=6, decimal_places=3, default=0, help_text="Duração do vídeo em minutos (precisão até milésimos).")
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.title} ({self.lesson.title})"


# ============================================================
#  ENROLLMENT
# ============================================================
class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(SchoolUser, on_delete=models.CASCADE, related_name='enrollments')

    status = models.CharField(
        max_length=20,
        choices=[('active', 'Ativo'), ('completed', 'Concluído')],
        default='active'
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'student')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.get_full_name()} em {self.course.title}"

    @property
    def progress(self):
        """Retorna a média de progresso do aluno neste curso"""
        progresses = Progress.objects.filter(course=self.course, student=self.student)
        return progresses.aggregate(avg=models.Avg('progress_percentage'))['avg'] or 0


# ============================================================
#  PROGRESSO DA AULA
# ============================================================
class Progress(models.Model):
    student = models.ForeignKey(SchoolUser, on_delete=models.CASCADE, related_name='course_progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='student_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='student_progress')

    is_completed = models.BooleanField(default=False)
    progress_percentage = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'lesson']
        ordering = ['-last_accessed']

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.lesson.title}"




# ============================================================
#  REVIEW
# ============================================================
class Review(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_reviews')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['course', 'student']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} - {self.course.title} ({self.rating}★)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        avg = self.course.reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        self.course.average_rating = round(avg, 2)
        self.course.save(update_fields=['average_rating'])




# ============================================================
#  ASSESSMENT / AVALIAÇÃO (APOL, prova, atividade etc.)
# ============================================================
class Assessment(models.Model):
    TYPE_CHOICES = [
        ("quiz", "Quiz / Objetiva"),
        ("apol", "APOL / Avaliação Oficial"),
        ("essay", "Dissertativa"),
        ("file_upload", "Envio de Arquivo"),
        ("practice", "Atividade Prática"),
        ("final_exam", "Prova Final"),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessments")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="assessments")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="quiz")

    weight = models.DecimalField(max_digits=5, decimal_places=2, default=10, help_text="Peso da nota em %")  # porcentagem da nota
    attempts_allowed = models.PositiveIntegerField(default=1, help_text="Número máximo de tentativas permitidas")
    time_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Tempo em minutos (opcional)")

    open_at = models.DateTimeField(null=True, blank=True)
    close_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.title
    
    @property
    def status(self):
        now = timezone.now()

        # Ainda não abriu
        if self.open_at and now < self.open_at:
            return "pending"

        # Já encerrou
        if self.close_at and now > self.close_at:
            return "closed"

        # Está aberta / ativa
        return "active"


# ============================================================
#  QUESTION
# ============================================================
class Question(models.Model):
    QUESTION_TYPES = [
        ('multiple_choice', 'Múltipla Escolha'),
        ('true_false', 'Verdadeiro ou Falso'),
        ('essay', 'Dissertativa'),
        ('file', 'Envio de Arquivo'),
    ]

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    type = models.CharField(max_length=20, choices=QUESTION_TYPES, default="multiple_choice")
    order = models.PositiveIntegerField(default=1)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    def __str__(self):
        return self.text[:50]


# ============================================================
#  CHOICE
# ============================================================
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.text[:50]


# ============================================================
#  ATTEMPT
# ============================================================
class Attempt(models.Model):
    student = models.ForeignKey(SchoolUser, on_delete=models.CASCADE, related_name="assessment_attempts")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="attempts")

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_submitted = models.BooleanField(default=False)

    attempt_number = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Tentativa {self.attempt_number} - {self.assessment.title}"


# ============================================================
#  ANSWER
# ============================================================
class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)

    choice = models.ForeignKey(Choice, null=True, blank=True, on_delete=models.SET_NULL)
    text_answer = models.TextField(blank=True)
    file_answer = models.FileField(upload_to="assessments/answers/", null=True, blank=True)

    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Resposta de {self.attempt.student}"


# ============================================================
#  PROFILE
# ============================================================
class Profile(models.Model):
    GENDER_CHOICES = [('M', 'Masculino'), ('F', 'Feminino'), ('O', 'Outro')]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='profiles/avatars/', blank=True, null=True)
    banner = models.ImageField(upload_to='profiles/banners/', blank=True, null=True)
    bio = models.TextField(blank=True, max_length=500)
    phone = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    location = models.CharField(max_length=100, blank=True)

    twitter = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    website = models.URLField(blank=True)

    theme = models.CharField(max_length=20, default='light')
    language = models.CharField(max_length=10, default='pt-BR')
    public_profile = models.BooleanField(default=True)
    show_progress = models.BooleanField(default=True)

    email_messages = models.BooleanField(default=True)
    email_course_updates = models.BooleanField(default=True)
    email_marketing = models.BooleanField(default=False)
    push_notifications = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.user.username}"


# ============================================================
#  CERTIFICATE
# ============================================================
class Certificate(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates')
    certificate_code = models.CharField(max_length=50, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    student_name = models.CharField(max_length=255)
    course_title = models.CharField(max_length=255)
    completion_date = models.DateField()
    instructor_name = models.CharField(max_length=255)
    template = models.CharField(max_length=50, default='default')

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-issued_at']

    def __str__(self):
        return f"Certificado: {self.student.username} - {self.course.title}"

    def save(self, *args, **kwargs):
        if not self.certificate_code:
            self.certificate_code = f"CERT-{uuid.uuid4().hex[:12].upper()}"
        if not self.student_name:
            self.student_name = self.student.get_full_name() or self.student.username
        if not self.course_title:
            self.course_title = self.course.title
        if not self.instructor_name:
            self.instructor_name = self.course.instructor.get_full_name() or self.course.instructor.username
        super().save(*args, **kwargs)


