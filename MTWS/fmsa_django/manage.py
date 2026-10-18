#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # 添加Django项目路径到sys.path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    django_dir = os.path.join(script_dir, '..', 'fmsa_django')
    sys.path.insert(0, django_dir)
    
    # 切换到Django项目目录
    os.chdir(django_dir)
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fmsa_system.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
