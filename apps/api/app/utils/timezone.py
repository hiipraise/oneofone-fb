from datetime import datetime, timedelta, timezone

WAT = timezone(timedelta(hours=1), name="WAT")


def now_wat() -> datetime:
    return datetime.now(WAT)
