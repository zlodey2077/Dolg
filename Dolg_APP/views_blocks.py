"""
API для Functional Blocks (killer-фича Lithium ECAD).

Endpoints:
    GET    /api/blocks/                — список блоков юзера + public
    POST   /api/blocks/                — создать новый блок
    GET    /api/blocks/<id>/           — детали (с schema_json для drag-n-drop)
    POST   /api/blocks/<id>/use/       — инкремент use_count при drag
    DELETE /api/blocks/<id>/           — удалить свой блок

2026-06-02: создано как часть Tier 0 killer-фич перед защитой.
"""

from __future__ import annotations
import json
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import FunctionalBlock


def _serialize_block(b: FunctionalBlock, include_schema: bool = False) -> dict:
    """Безопасная сериализация без schema_json по умолчанию (он тяжёлый)."""
    out = {
        'id': b.id,
        'name': b.name,
        'description': b.description,
        'category': b.category,
        'category_label': b.get_category_display(),
        'component_count': b.component_count,
        'connection_count': b.connection_count,
        'use_count': b.use_count,
        'is_public': b.is_public,
        'is_mine': True,  # переписывается в list-view ниже
        'created_at': b.created_at.isoformat(),
        'updated_at': b.updated_at.isoformat(),
        'preview_svg': b.preview_svg or '',
    }
    if include_schema:
        out['schema_json'] = b.schema_json
    return out


@login_required
@require_GET
def api_blocks_list(request):
    """Список блоков: свои + public других."""
    qs = FunctionalBlock.objects.filter(
        Q(user=request.user) | Q(is_public=True)
    ).select_related('user').order_by('-updated_at')

    category = request.GET.get('category', '').strip()
    if category:
        qs = qs.filter(category=category)

    blocks = []
    for b in qs[:200]:  # cap
        item = _serialize_block(b)
        item['is_mine'] = (b.user_id == request.user.id)
        item['author'] = b.user.username if not item['is_mine'] else None
        blocks.append(item)

    return JsonResponse({
        'ok': True,
        'blocks': blocks,
        'total': len(blocks),
        'categories': [
            {'value': v, 'label': l} for v, l in FunctionalBlock.CATEGORY_CHOICES
        ],
    })


@login_required
@require_POST
def api_blocks_create(request):
    """Создание блока. Body: {name, description, category, schema_json, preview_svg?}."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Невалидный JSON'}, status=400)

    name = (data.get('name') or '').strip()
    if not name or len(name) > 80:
        return JsonResponse({'ok': False, 'error': 'Имя обязательно (1-80 символов)'}, status=400)

    schema = data.get('schema_json') or {}
    if not isinstance(schema, dict) or 'components' not in schema:
        return JsonResponse(
            {'ok': False, 'error': 'schema_json должен содержать components и connections'},
            status=400,
        )
    components = schema.get('components') or []
    if not components:
        return JsonResponse({'ok': False, 'error': 'Блок не может быть пустым'}, status=400)
    if len(components) > 200:
        return JsonResponse({'ok': False, 'error': 'Слишком большой блок (>200 компонентов)'}, status=400)

    block = FunctionalBlock.objects.create(
        name=name,
        description=(data.get('description') or '').strip()[:200],
        category=data.get('category') or 'other',
        schema_json=schema,
        preview_svg=(data.get('preview_svg') or '')[:50000],  # max 50KB SVG
        user=request.user,
        is_public=bool(data.get('is_public')),
    )
    return JsonResponse({
        'ok': True,
        'block': _serialize_block(block),
    })


@login_required
@require_GET
def api_blocks_detail(request, block_id: int):
    """Детали блока — включает schema_json для drag-n-drop."""
    block = get_object_or_404(
        FunctionalBlock,
        Q(pk=block_id) & (Q(user=request.user) | Q(is_public=True)),
    )
    item = _serialize_block(block, include_schema=True)
    item['is_mine'] = (block.user_id == request.user.id)
    return JsonResponse({'ok': True, 'block': item})


@login_required
@require_POST
def api_blocks_use(request, block_id: int):
    """Инкремент use_count при drag в схему. Не возвращает schema (детали уже есть)."""
    block = get_object_or_404(
        FunctionalBlock,
        Q(pk=block_id) & (Q(user=request.user) | Q(is_public=True)),
    )
    FunctionalBlock.objects.filter(pk=block.pk).update(use_count=block.use_count + 1)
    return JsonResponse({'ok': True, 'use_count': block.use_count + 1})


@login_required
@require_http_methods(['DELETE'])
def api_blocks_delete(request, block_id: int):
    """Удалить свой блок. Чужие public не удалит."""
    block = get_object_or_404(FunctionalBlock, pk=block_id, user=request.user)
    block.delete()
    return JsonResponse({'ok': True})
