# -*- coding: utf-8 -*-
"""Resolucion de periodos relativos a rangos de fecha concretos.

El LLM nunca calcula fechas: se limita a nombrar un periodo
("last_3_months", "next_15_days", "this_month", ...) y aqui se traduce
a un par (inicio, fin) con el momento actual como referencia.

Compras mira hacia adelante tanto como hacia atras ("que llega la semana que
viene", "que deberia haber llegado ya"), asi que hay periodos de futuro y
periodos ABIERTOS por un extremo: `until_now` no tiene inicio y `from_now` no
tiene fin. En esos casos el limite ausente viaja como None y
`period_to_domain` emite un solo leaf.

Sin dependencias de Odoo: solo datetime + python-dateutil (incluido en Odoo).
"""
import re
from datetime import datetime

from dateutil.relativedelta import relativedelta

# Formato que entiende el ORM para campos Datetime (y tambien Date).
_FMT = "%Y-%m-%d %H:%M:%S"

# Periodos con nombre fijo. Valor = funcion(ref) -> (inicio, fin_exclusivo).
# Convencion: rango semiabierto [inicio, fin)  ->  domain: >= inicio AND < fin.
_NAMED = {
    "today": lambda r: (_start_of_day(r), _start_of_day(r) + relativedelta(days=1)),
    "yesterday": lambda r: (_start_of_day(r) - relativedelta(days=1), _start_of_day(r)),
    "this_week": lambda r: (_start_of_day(r) - relativedelta(days=r.weekday()),
                            _start_of_day(r) - relativedelta(days=r.weekday()) + relativedelta(weeks=1)),
    "this_month": lambda r: (r.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                             r.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + relativedelta(months=1)),
    "last_month": lambda r: (r.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - relativedelta(months=1),
                             r.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),
    "this_quarter": lambda r: (_start_of_quarter(r), _start_of_quarter(r) + relativedelta(months=3)),
    "last_quarter": lambda r: (_start_of_quarter(r) - relativedelta(months=3), _start_of_quarter(r)),
    "this_year": lambda r: (r.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
                            r.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0) + relativedelta(years=1)),

    # --- Hacia adelante ---------------------------------------------------
    "tomorrow": lambda r: (_start_of_day(r) + relativedelta(days=1),
                           _start_of_day(r) + relativedelta(days=2)),
    "next_week": lambda r: (_start_of_week(r) + relativedelta(weeks=1),
                            _start_of_week(r) + relativedelta(weeks=2)),
    "next_month": lambda r: (_start_of_month(r) + relativedelta(months=1),
                             _start_of_month(r) + relativedelta(months=2)),
    "next_quarter": lambda r: (_start_of_quarter(r) + relativedelta(months=3),
                               _start_of_quarter(r) + relativedelta(months=6)),

    # --- Abiertos por un extremo -----------------------------------------
    # `until_now` es lo que en Compras se llama "atrasado": fecha prevista ya
    # pasada. Que ademas siga pendiente es un filtro de estado, no de fecha.
    "until_now": lambda r: (None, r),
    "until_today": lambda r: (None, _start_of_day(r)),
    "from_now": lambda r: (r, None),
    "from_today": lambda r: (_start_of_day(r), None),
}

# Periodos parametricos: last_<n>_days / last_<n>_months / last_<n>_weeks / last_<n>_years
_TRAILING_RE = re.compile(r"^last_(\d{1,4})_(day|days|week|weeks|month|months|year|years)$")
# ... y sus simetricos hacia el futuro: next_<n>_days / next_<n>_weeks / ...
_LEADING_RE = re.compile(r"^next_(\d{1,4})_(day|days|week|weeks|month|months|year|years)$")
_UNIT_TO_KW = {
    "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months",
    "year": "years", "years": "years",
}


class PeriodError(ValueError):
    """Periodo no reconocido o mal formado."""


def _start_of_day(ref):
    return ref.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(ref):
    return _start_of_day(ref) - relativedelta(days=ref.weekday())


def _start_of_month(ref):
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_quarter(ref):
    first_month = ((ref.month - 1) // 3) * 3 + 1
    return ref.replace(month=first_month, day=1, hour=0, minute=0, second=0, microsecond=0)


def supported_periods():
    """Lista legible de periodos aceptados (para el prompt del LLM)."""
    return sorted(_NAMED.keys()) + [
        "last_<n>_days", "last_<n>_weeks", "last_<n>_months", "last_<n>_years",
        "next_<n>_days", "next_<n>_weeks", "next_<n>_months", "next_<n>_years",
    ]


def resolve_range(period, ref=None):
    """Devuelve (inicio, fin) como strings 'YYYY-MM-DD HH:MM:SS'.

    Rango semiabierto: usar en un domain como
        [(campo, '>=', inicio), (campo, '<', fin)]

    Un extremo puede ser None en los periodos abiertos (`until_now`,
    `from_now`): entonces ese lado no acota nada.

    :param period: str, p.ej. 'last_3_months', 'this_month', 'last_10_days'
    :param ref: datetime de referencia (por defecto: ahora). Util en tests.
    """
    if not period or not isinstance(period, str):
        raise PeriodError("El periodo debe ser una cadena no vacia.")
    period = period.strip().lower()
    ref = ref or datetime.now()

    if period in _NAMED:
        start, end = _NAMED[period](ref)
        return (start.strftime(_FMT) if start else None,
                end.strftime(_FMT) if end else None)

    m = _TRAILING_RE.match(period)
    if m:
        n = int(m.group(1))
        if n <= 0:
            raise PeriodError("El numero de unidades debe ser mayor que cero: %r" % period)
        kw = _UNIT_TO_KW[m.group(2)]
        start = ref - relativedelta(**{kw: n})
        return start.strftime(_FMT), ref.strftime(_FMT)

    m = _LEADING_RE.match(period)
    if m:
        n = int(m.group(1))
        if n <= 0:
            raise PeriodError("El numero de unidades debe ser mayor que cero: %r" % period)
        kw = _UNIT_TO_KW[m.group(2)]
        end = ref + relativedelta(**{kw: n})
        return ref.strftime(_FMT), end.strftime(_FMT)

    raise PeriodError(
        "Periodo no reconocido: %r. Validos: %s" % (period, ", ".join(supported_periods()))
    )


def period_to_domain(field, period, ref=None):
    """Atajo: devuelve los dos leaves de domain para acotar `field` a `period`."""
    start, end = resolve_range(period, ref=ref)
    leaves = []
    if start is not None:
        leaves.append((field, ">=", start))
    if end is not None:
        leaves.append((field, "<", end))
    return leaves
