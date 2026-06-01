# DOLG Moderation And Roles

Дата: 2026-05-26

## Что добавлено

- Новый app `moderation`: жалобы, moderation cases, действия модератора, ограничения пользователей и правила модерации.
- Глобальные группы Django:
  - `site_admin`
  - `site_moderator`
  - `catalog_editor`
  - `knowledge_editor`
  - `support_agent`
- Локальная роль команды: `moderator` с правом `org.moderation.manage`.
- Soft moderation для `Comment`, `ChatTopic`, `ChatReply`, `OrgConversationMessage`.
- API:
  - `POST /api/moderation/report/`
  - `GET /api/moderation/queue/`
  - `POST /api/moderation/cases/<id>/action/`
- Внутренняя очередь: `/moderation/`.

## Поведение V1

- Обычные пользователи видят только `moderation_status="visible"`.
- Staff, superuser и глобальные модераторы могут видеть очередь и выполнять действия.
- Org-модератор работает только с объектами своей команды.
- Удаление комментария теперь soft-delete: статус `removed`; физический purge доступен только superuser.
- `UserRestriction` с типом `mute`, `ban` или `read_only` блокирует создание Q&A-топиков, ответов и комментариев.

## Проверки

```bash
python manage.py check
python manage.py test moderation.tests --verbosity 2
python manage.py check_demo_ready --json
```

`check_demo_ready` содержит блок `moderation_stack`: роли, soft-fields, URL API и модели moderation core.
