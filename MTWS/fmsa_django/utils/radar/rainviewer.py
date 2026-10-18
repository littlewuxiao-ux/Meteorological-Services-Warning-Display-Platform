"""RainViewer Weather Maps 客户端（个人/教育瓦片）。"""

from __future__ import annotations

import logging
import time
from typing import Dict, Iterable, Optional, Tuple

import requests

from .rate_limiter import get_rate_limiter

logger = logging.getLogger('fmsa.radar.rainviewer')

MAPS_URL = 'https://api.rainviewer.com/public/weather-maps.json'
TileKey = Tuple[int, int, int]  # z, x, y


class RainViewerRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__('RainViewer rate limited')
        self.retry_after = float(retry_after)


class RainViewerClient:
    def __init__(self, rate_limit_per_minute: int = 80, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.limiter = get_rate_limiter()
        self.limiter.configure(rate_limit_per_minute)

    def fetch_maps(self) -> dict:
        self._wait_slot()
        resp = self.session.get(MAPS_URL, timeout=30)
        if resp.status_code == 429:
            self.limiter.note_429()
            raise RuntimeError('RainViewer rate limited (429) on maps.json')
        resp.raise_for_status()
        return resp.json()

    def latest_frame(self, maps: Optional[dict] = None) -> Tuple[str, str, int]:
        """返回 (host, path, unix_time)。"""
        data = maps or self.fetch_maps()
        host = data.get('host') or 'https://tilecache.rainviewer.com'
        past = (data.get('radar') or {}).get('past') or []
        if not past:
            raise RuntimeError('RainViewer past frames empty')
        frame = past[-1]
        return host.rstrip('/'), frame['path'], int(frame['time'])

    def tile_url(
        self,
        host: str,
        path: str,
        z: int,
        x: int,
        y: int,
        tile_size: int = 256,
        color: int = 2,
        smooth: int = 0,
        snow: int = 0,
    ) -> str:
        return f'{host}{path}/{tile_size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png'

    def download_tile(
        self,
        host: str,
        path: str,
        z: int,
        x: int,
        y: int,
        tile_size: int = 256,
        color: int = 2,
        smooth: int = 0,
        snow: int = 0,
        retries: int = 5,
    ) -> bytes:
        url = self.tile_url(host, path, z, x, y, tile_size, color, smooth, snow)
        backoff = 5.0
        last_err: Optional[Exception] = None
        for _ in range(retries):
            self._wait_slot()
            try:
                resp = self.session.get(url, timeout=30)
            except requests.RequestException as e:
                last_err = e
                logger.warning('tile download error %s: %s', url, e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if resp.status_code == 429:
                self.limiter.note_429(backoff_seconds=backoff)
                logger.warning('429 on tile, backoff %.1fs', backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if resp.status_code >= 500:
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            resp.raise_for_status()
            return resp.content
        raise RuntimeError(f'Failed to download tile after retries: {url}; last={last_err}')

    def download_tiles(
        self,
        host: str,
        path: str,
        z: int,
        tiles: Iterable[Tuple[int, int]],
        tile_size: int = 256,
        color: int = 2,
        smooth: int = 0,
        snow: int = 0,
        cache: Optional[Dict[TileKey, bytes]] = None,
    ) -> Dict[TileKey, bytes]:
        """下载 z 级瓦片；cache 可跨层复用同一帧。"""
        out: Dict[TileKey, bytes] = {}
        cache = cache if cache is not None else {}
        pending = []
        for x, y in tiles:
            key = (int(z), int(x), int(y))
            if key in cache:
                out[key] = cache[key]
            else:
                pending.append(key)
        self.limiter.set_queued(len(pending))
        for i, key in enumerate(pending):
            self.limiter.set_queued(len(pending) - i)
            z0, x0, y0 = key
            data = self.download_tile(host, path, z0, x0, y0, tile_size, color, smooth, snow)
            cache[key] = data
            out[key] = data
        self.limiter.set_queued(0)
        return out

    def latest_frame_reserved(self) -> Tuple[str, str, int]:
        """调用方已占用 1 个名额。不再次限流。"""
        resp = self._get_reserved(MAPS_URL)
        resp.raise_for_status()
        return self.latest_frame(resp.json())

    def download_tiles_reserved(
        self,
        host: str,
        path: str,
        z: int,
        tiles: Iterable[Tuple[int, int]],
        tile_size: int = 256,
        color: int = 2,
        smooth: int = 0,
        snow: int = 0,
    ) -> Dict[TileKey, bytes]:
        """调用方已按瓦片数占用名额。429 抛 RainViewerRateLimited，404 跳过。"""
        out: Dict[TileKey, bytes] = {}
        for x, y in tiles:
            url = self.tile_url(host, path, z, x, y, tile_size, color, smooth, snow)
            try:
                resp = self._get_reserved(url)
            except requests.RequestException as e:
                raise RuntimeError(f'下载雷达瓦片失败: {url}; {e}') from e
            if resp.status_code == 404:
                continue
            if resp.status_code >= 500:
                raise RuntimeError(f'雷达瓦片服务异常 ({resp.status_code})')
            resp.raise_for_status()
            out[(int(z), int(x), int(y))] = resp.content
        return out

    def _get_reserved(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 429:
            self.limiter.note_429()
            paused = float(self.limiter.status().get('paused_seconds') or 30)
            raise RainViewerRateLimited(paused)
        return resp

    def _wait_slot(self) -> None:
        if not self.limiter.acquire(timeout=600):
            raise RuntimeError('Rate limiter acquire timeout')
