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
from utils.cas_api_log import cas_user_context
from utils.module_profile import REPORT_LANG_CHINESE, report_lang

logger = logging.getLogger('fmsa.api')


def _plain_tz_from_request(request) -> str:
    tz = str(request.GET.get('tz') or '').strip().upper()
    return 'UTC' if tz == 'UTC' else 'CST'

PLAIN_MODULE = 'view_plain'


def _deny_if_no_access(request):
    identity = resolve_access_identity(request)
    if has_perm(identity, PLAIN_MODULE, 'display'):
        return None
    if report_lang() == REPORT_LANG_CHINESE:
        return None
    return JsonResponse({'success': False, 'error': '无权访问中文模式'}, status=403)


def _latest_taf_elements(codes: list) -> dict:
    """每个机场最新一份 TAF 的 taf_elements：先取每场最大 id，再回表取列。"""
    from runtime_db.models import Taf

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


def _soft_token(request, time_mode: str):
    """批量翻译缺库时补拉实时报文用。没有 token 就跳过，不把整批打成 401。"""
    if time_mode != 'current':
        return None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    try:
        from parsers.scheduler import get_scheduler_token
        return get_scheduler_token()
    except Exception:
        return None


def _df_for_code(df, code: str):
    if df is None or getattr(df, 'empty', True):
        return None
    if 'airport4Code' not in df.columns:
        return None
    matched = df[df['airport4Code'].astype(str).str.strip().str.upper() == code]
    if matched is None or matched.empty:
        return None
    return matched


def _live_taf_row(code: str, time_mode: str, token):
    """清单外机场不入库，按搜索同一路实时解析出 taf_elements。"""
    try:
        from data_adapters.adapter_factory import AdapterFactory
        from parsers.taf_parser import TafParser

        adapter = AdapterFactory.create_adapter(time_mode=time_mode, token=token)
        taf_df = _df_for_code(adapter.get_taf_data([code]), code)
        if taf_df is None:
            return None
        row = taf_df.iloc[0]
        taf_content = str(row.get('content', '')).strip()
        if not taf_content:
            return None
        parser = TafParser(time_mode=time_mode, token=token)
        if not parser.parse_taf(taf_content, code):
            return None
        raw_obs_time = row.get('observationTime', '')
        try:
            parser.observation_time = int(float(raw_obs_time)) if raw_obs_time not in ('', None) else None
        except (TypeError, ValueError):
            parser.observation_time = None
        data = parser.to_database_dict()
        return {
            'airport_4code': code,
            'taf_elements': data.get('taf_elements'),
            'data_status': 'N',
            'import_alert': 'N',
        }
    except Exception as exc:
        logger.warning(f'实时预报明语失败 [{code}]: {exc}')
        return None


def _live_metar_row(code: str, time_mode: str, token):
    """清单外机场不入库，按搜索同一路实时解析出 metar_elements。"""
    try:
        from data_adapters.adapter_factory import AdapterFactory
        from parsers.metar_parser import MetarParser

        adapter = AdapterFactory.create_adapter(time_mode=time_mode, token=token)
        metar_df = _df_for_code(adapter.get_metar_data([code]), code)
        if metar_df is None:
            return None
        parser = MetarParser(time_mode=time_mode, token=token)
        for _, row in metar_df.iterrows():
            try:
                parsed = parser._parse_metar_content(row)
            except Exception as exc:
                logger.debug(f'实时实况解析失败 [{code}]: {exc}')
                continue
            if not parsed or not parsed.get('metar_elements'):
                continue
            return {
                'airport_4code': code,
                'metar_elements': parsed.get('metar_elements'),
                'data_status': 'N',
                'sqc': str(row.get('sqc', '')).strip() or None,
            }
        return None
    except Exception as exc:
        logger.warning(f'实时实况明语失败 [{code}]: {exc}')
        return None


def _elements_ready(row: dict | None, field: str) -> bool:
    if not row:
        return False
    if row.get('data_status') == 'C':
        return True
    return bool(row.get(field))


def _latest_metar_elements(codes: list) -> dict:
    """每个机场当前 N 行的 metar_elements。"""
    from runtime_db.models import Metar

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
        missing = [c for c in codes if not _elements_ready(rows.get(c), 'taf_elements')]
        if missing:
            from .airport_extra_views import _cas_user_from_request
            token = _soft_token(request, time_mode)
            with cas_user_context(_cas_user_from_request(request)):
                for code in missing:
                    live = _live_taf_row(code, time_mode, token)
                    if live:
                        rows[code] = live
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
        missing = [c for c in codes if not _elements_ready(rows.get(c), 'metar_elements')]
        if missing:
            from .airport_extra_views import _cas_user_from_request
            token = _soft_token(request, time_mode)
            with cas_user_context(_cas_user_from_request(request)):
                for code in missing:
                    live = _live_metar_row(code, time_mode, token)
                    if live:
                        rows[code] = live
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
