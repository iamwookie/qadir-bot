from datetime import datetime, timezone


def dt_to_psx(dt: datetime) -> float:
    """
    Convert a datetime object to a POSIX timestamp (seconds since epoch).

    Args:
        dt (datetime): The datetime object to convert.

    Returns:
        float: The POSIX timestamp.
    """

    return float(dt.timestamp())


def psx_to_dt(posix: float) -> datetime:
    """
    Convert a POSIX timestamp (seconds since epoch) to a datetime object.

    Args:
        posix (float): The POSIX timestamp to convert.

    Returns:
        datetime: The corresponding datetime object.
    """

    return datetime.fromtimestamp(posix, tz=timezone.utc)