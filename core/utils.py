import datetime


def datetime_to_posix(dt: datetime.datetime) -> int:
    """
    Convert a datetime object to a POSIX timestamp (seconds since epoch).

    Args:
        dt (datetime.datetime): The datetime object to convert.

    Returns:
        int: The POSIX timestamp.
    """

    return int(dt.timestamp())
