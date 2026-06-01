from django.db.models import Q

from shop.component_validation import missing_spice_model_warning, nominal_mismatch_warning
from shop.models import Product

COMPONENT_TO_CATEGORY = {
    'resistor': 'resistors',
    'capacitor': 'capacitors',
    'inductor': 'inductors',
    'diode': 'diodes',
    'led': 'diodes',
    'transistor': 'transistors',
    'npn': 'transistors',
    'pnp': 'transistors',
    'ic': 'ics',
    'connector': 'connectors',
    'relay': 'relays',
    'switch': 'relays',
}


def validate_scheme_data(scheme_data):
    components = scheme_data.get('components', []) if isinstance(scheme_data, dict) else []
    connections = scheme_data.get('connections', []) if isinstance(scheme_data, dict) else []
    errors = []
    warnings = []

    if not isinstance(components, list):
        errors.append('components должен быть массивом')
        components = []
    if not isinstance(connections, list):
        errors.append('connections должен быть массивом')
        connections = []

    ids = []
    for component in components:
        if not isinstance(component, dict):
            errors.append('Компонент должен быть объектом')
            continue
        if component.get('id') is None:
            errors.append('У компонента отсутствует id')
            continue
        ids.append(component['id'])
        component_type = (component.get('type') or '').lower()
        catalog_ref = (component.get('catalog_ref') or component.get('part_number') or '').strip()
        product = None
        if catalog_ref:
            product = Product.objects.filter(
                Q(part_number__iexact=catalog_ref) | Q(slug__iexact=catalog_ref)
            ).select_related('category').first()
            if not product:
                warnings.append(f'Компонент #{component["id"]}: товар каталога "{catalog_ref}" не найден')
            else:
                expected_category = COMPONENT_TO_CATEGORY.get(component_type)
                if expected_category and product.category.slug != expected_category:
                    warnings.append(
                        f'Компонент #{component["id"]}: товар "{catalog_ref}" относится к '
                        f'категории {product.category.slug}, ожидается {expected_category}'
                    )
                nominal_warning = nominal_mismatch_warning(component, product)
                if nominal_warning:
                    warnings.append(f'Компонент #{component["id"]}: {nominal_warning}')

        spice_warning = missing_spice_model_warning(component, product)
        if spice_warning:
            warnings.append(f'Компонент #{component["id"]}: {spice_warning}')

    duplicate_ids = {item for item in ids if ids.count(item) > 1}
    for item in sorted(duplicate_ids, key=str):
        errors.append(f'Дублирующийся id компонента: {item}')

    id_set = set(ids)
    used_component_ids = set()
    for connection in connections:
        if not isinstance(connection, dict):
            errors.append('Соединение должно быть объектом')
            continue
        source = connection.get('from') or {}
        target = connection.get('to') or {}
        source_id = source.get('compId')
        target_id = target.get('compId')
        if source_id not in id_set or target_id not in id_set:
            errors.append('Соединение ссылается на отсутствующий компонент')
            continue
        if source_id == target_id:
            errors.append(f'Провод соединяет компонент #{source_id} сам с собой')
        used_component_ids.update([source_id, target_id])

    if components and not any(c.get('type') == 'ground' for c in components if isinstance(c, dict)):
        warnings.append('В схеме нет GND: симулятор назначит опорный узел автоматически')
    if components and not any(c.get('type') == 'battery' for c in components if isinstance(c, dict)):
        warnings.append('В схеме нет источника питания')

    unconnected = [
        c.get('id') for c in components
        if isinstance(c, dict) and c.get('type') not in {'ground', 'node'} and c.get('id') not in used_component_ids
    ]
    if unconnected:
        warnings.append(f'Есть компоненты без соединений: {", ".join(map(str, unconnected[:8]))}')

    return {'ok': not errors, 'errors': errors, 'warnings': warnings}
