"""
cache_driver — WebHelper 的缓存驱动。

抽象 ``CacheDriver``(get / set / delete，带可设 TTL)
底层用diskcache(磁盘持久、跨进程安全、自带过期)。因为 web_helper 是短命进程,

调用方直接用模块级单例 ``cache``,不用自己 new:

    from web_helper_tools.cache_driver import cache

    cache.set("key", value, ttl=3600)   # 不传 ttl 用默认
    hit = cache.get("key")              # 未命中 / 已过期 → None
    cache.delete("key")

想换底层(redis / 内存 …)只需另写一个实现 ``CacheDriver`` 的类,调用方一行不改。
"""
from typing import Any, Optional, Protocol
import diskcache

from config import CACHE_DEFAULT_TTL, CACHE_DEFAULT_DIR


# 默认 TTL 与缓存目录(项目根 web_helper/.webhelper_cache/)。


class CacheDriver(Protocol):
    """缓存驱动抽象。换底层存储不动调用方。"""

    def get(self, key: str) -> Optional[Any]:
        """未命中或已过期返回 None。"""
        ...

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """ttl 为秒;None 时用驱动的默认 TTL。"""
        ...

    def delete(self, key: str) -> None:
        """删一条,不存在则无操作。"""
        ...


class DiskCacheDriver:
    """diskcache 实现:磁盘持久、跨进程安全、按 expire 自动过期。"""

    def __init__(self, directory: str = CACHE_DEFAULT_DIR, default_ttl: int = CACHE_DEFAULT_TTL) -> None:
        self._cache = diskcache.Cache(directory)
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._cache.set(key, value, expire=self._default_ttl if ttl is None else ttl)

    def delete(self, key: str) -> None:
        self._cache.delete(key)


# 默认单例:import 即用。
cache: CacheDriver = DiskCacheDriver()
