import hashlib

from django.db import migrations


def _looks_hashed(token: str) -> bool:
    return len(token) == 64 and all(ch in '0123456789abcdef' for ch in token)


def hash_plaintext_api_tokens(apps, schema_editor):
    OrganizationApiToken = apps.get_model('Dolg_APP', 'OrganizationApiToken')
    for api_token in OrganizationApiToken.objects.only('id', 'token'):
        if api_token.token and _looks_hashed(api_token.token):
            continue
        if not api_token.token:
            continue
        api_token.token = hashlib.sha256(api_token.token.encode('utf-8')).hexdigest()
        api_token.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('Dolg_APP', '0018_mljob'),
    ]

    operations = [
        migrations.RunPython(hash_plaintext_api_tokens, migrations.RunPython.noop),
    ]
