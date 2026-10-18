import json

from django.conf import settings


def alert_colors(request):
    colors = getattr(settings, 'ALERT_COLORS', {})
    return {
        'alert_colors': colors,
        'alert_colors_json': json.dumps(colors),
    }
