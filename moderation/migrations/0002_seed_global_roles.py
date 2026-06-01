from django.db import migrations


GLOBAL_GROUPS = [
    'site_admin',
    'site_moderator',
    'catalog_editor',
    'knowledge_editor',
    'support_agent',
]


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in GLOBAL_GROUPS:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=GLOBAL_GROUPS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('moderation', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
