# Django i18n catalogs (EN/FR)

This directory contains backend translation catalogs for Django:
- `locale/fr/LC_MESSAGES/django.po`
- `locale/en/LC_MESSAGES/django.po`

## Update workflow

1. Mark backend strings in Python with `gettext`/`gettext_lazy`.
2. Extract messages:
   - `python manage.py makemessages -l fr -l en`
3. Translate `msgstr` entries in each `.po` file.
4. Compile catalogs:
   - `python manage.py compilemessages`

## Note

On Windows, `makemessages` and `compilemessages` require GNU gettext tools
(`msguniq`, `msgfmt`, etc.) installed and available in `PATH`.
