"""Redis istemcisi (async). Sağlık kontrolü, önbellek ve oran sınırlama için kullanılır.

Celery kendi Redis bağlantısını ayrıca yönetir; bu istemci yalnızca API sürecine aittir.
"""

from redis.asyncio import Redis


def create_redis(url: str, timeout_s: float = 2.0) -> Redis:
    # Bağlantı tembel kurulur; Redis kapalıysa uygulama yine açılır, /health/ready bunu gösterir.
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=timeout_s,
        socket_timeout=timeout_s,
    )
