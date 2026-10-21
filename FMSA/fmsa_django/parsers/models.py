"""生产报文模型已移到 runtime_db。这里只转接旧引用。"""

from runtime_db.models import Flight, Metar, Taf, UserAirportAlert

__all__ = ['Flight', 'Metar', 'Taf', 'UserAirportAlert']
