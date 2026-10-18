"""中文（明语）模式 API。

只读：批量预报/实况明语只取最小单元 JSON 列，翻译后返回；
详情页中文报文与原文接口同一批原始报文，输出中文。不写库、不改主页接口。
"""

from __future__ import annotations

import logging

from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from utils.access_control import has_perm, resolve_access_identity

logger = logging.getLogger('fmsa.api')


def _plain_tz_from_request(request) -> str:
    tz = str(request.GET.get('tz') or '').strip().upper()
    return 'UTC' if tz == 'UTC' else 'CST'

PLAIN_MODULE = 'view_plain'


def _deny_if_no_access(request):
    identity = resolve_access_identity(request)
    if identity.get('needs_role_select'):
        return JsonResponse({'success': False, 'error': '请先选择角色'}, status=403)
    if not has_perm(identity, PLAIN_MODULE, 'display'):
        return JsonResponse({'success': False, 'error': '无权访问中文模式'}, status=403)
    return None


def _latest_taf_elements(codes: list) -> dict:
    """每个机场最新一份 TAF 的 taf_elements：先取每场最大 id，再回表取列。"""
    from parsers.models import Taf

    if not codes:
        return {}
    latest_ids = (
        Taf.objects.filter(airport_4code__in=codes)
        .values('airport_4code')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    rows = Taf.objects.filter(id__in=list(latest_ids)).values(
        'airport_4code', 'taf_elements', 'data_status', 'import_alert'
    )
    return {row['airport_4code']: row for row in rows}


def _latest_metar_elements(codes: list) -> dict:
    """每个机场当前 N 行的 metar_elements。"""
    from parsers.models import Metar

    if not codes:
        return {}
    rows = (
        Metar.objects.filter(airport_4code__in=codes, data_status='N')
        .order_by('airport_4code', '-created_at')
        .values('airport_4code', 'metar_elements', 'data_status', 'sqc')
    )
    result = {}
    for row in rows:
        result.setdefault(row['airport_4code'], row)
    return result


@require_http_methods(['GET'])
def plain_taf_batch(request, time_mode='current'):
    """GET ?codes=ZBAA,ZGSZ → 每个机场的预报明语（含甘特条带查表）。"""
    denied = _deny_if_no_access(request)
    if denied:
        return denied

    try:
        from parsers.plain_language import plain_display_timezone, translate_taf_row

        tz = _plain_tz_from_request(request)

        codes_param = request.GET.get('codes', '').strip()
        if codes_param:
            codes = [c.strip().upper() for c in codes_param.split(',') if len(c.strip()) == 4]
        else:
            from utils.airport_scope import get_monitored_airport_codes
            codes = get_monitored_airport_codes()
        codes = list(dict.fromkeys(codes))
        if not codes:
            return JsonResponse({'success': True, 'data': {}})

        rows = _latest_taf_elements(codes)
        result = {}
        with plain_display_timezone(tz):
            for code in codes:
                row = rows.get(code)
                if not row:
                    result[code] = None
                    continue
                if row.get('data_status') == 'C':
                    result[code] = None
                    continue
                try:
                    result[code] = translate_taf_row(row)
                except Exception as exc:
                    logger.error(f'预报明语翻译失败 [{code}]: {exc}')
                    result[code] = None
        return JsonResponse({'success': True, 'data': result})
    except Exception as exc:
        logger.error(f'批量预报明语失败: {exc}')
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@require_http_methods(['GET'])
def plain_metar_batch(request, time_mode='current'):
    """GET ?codes=ZBAA,ZGSZ → 每个机场的实况明语（列表行 + 详情甘特左侧短句）。"""
    denied = _deny_if_no_access(request)
    if denied:
        return denied

    try:
        from parsers.plain_language import plain_display_timezone, translate_metar_row

        tz = _plain_tz_from_request(request)

        codes_param = request.GET.get('codes', '').strip()
        if codes_param:
            codes = [c.strip().upper() for c in codes_param.split(',') if len(c.strip()) == 4]
        else:
            from utils.airport_scope import get_monitored_airport_codes
            codes = get_monitored_airport_codes()
        codes = list(dict.fromkeys(codes))
        if not codes:
            return JsonResponse({'success': True, 'data': {}})

        rows = _latest_metar_elements(codes)
        result = {}
        with plain_display_timezone(tz):
            for code in codes:
                row = rows.get(code)
                if not row or row.get('data_status') == 'C':
                    result[code] = None
                    continue
                try:
                    result[code] = translate_metar_row(row)
                except Exception as exc:
                    logger.error(f'实况明语翻译失败 [{code}]: {exc}')
                    result[code] = None
        return JsonResponse({'success': True, 'data': result})
    except Exception as exc:
        logger.error(f'批量实况明语失败: {exc}')
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@require_http_methods(['GET'])
def plain_report_text(request, airport_code, time_mode='current'):
    """详情页实况/预报区中文化：与 report-text 同源，仅输出改为中文。"""
    denied = _deny_if_no_access(request)
    if denied:
        return denied

    try:
        from .airport_extra_views import _cas_user_from_request, _resolve_cas_token
        from parsers.plain_language import build_airport_detail_plain_reports
        from utils.cas_api_log import cas_user_context

        token, err = _resolve_cas_token(request, time_mode)
        if err:
            return err
        with cas_user_context(_cas_user_from_request(request)):
            data = build_airport_detail_plain_reports(
                airport_code, time_mode=time_mode, token=token
            )
        return JsonResponse({'success': True, 'data': data})
    except Exception as exc:
        logger.error(f'详情页中文报文失败 [{airport_code}]: {exc}')
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
