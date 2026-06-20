from django.urls import path, register_converter
from django.urls.converters import SlugConverter

from Dolg_PR.url_utils import lazy_view


class UnicodeSlugConverter(SlugConverter):
    """Как обычный <slug:...>, но разрешает Unicode-буквы (\\w).
    Нужно потому, что slugify(..., allow_unicode=True) оставляет кириллицу."""

    regex = r'[-\w]+'


register_converter(UnicodeSlugConverter, 'uslug')


app_name = 'knowledge'

urlpatterns = [
    path('', lazy_view('knowledge.views.index'), name='index'),
    path('lab/', lazy_view('knowledge.views.engineering_lab'), name='engineering_lab'),
    path('lab/api/', lazy_view('knowledge.views.engineering_lab_api'), name='engineering_lab_api'),
    path('learning/', lazy_view('knowledge.views.learning_index'), name='learning_index'),
    path(
        'learning/<uslug:slug>/', lazy_view('knowledge.views.learning_lesson_detail'), name='learning_lesson'
    ),
    path(
        'learning/<uslug:slug>/task/<int:task_id>/check/',
        lazy_view('knowledge.views.learning_task_check'),
        name='learning_task_check',
    ),
    path('category/<uslug:slug>/', lazy_view('knowledge.views.category_detail'), name='category'),
    path('article/<uslug:slug>/', lazy_view('knowledge.views.article_detail'), name='article'),
]
