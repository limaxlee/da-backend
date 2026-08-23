from datetime import datetime, timezone

from data_agent.utils.date import convert_unix_to_datetime

TIMESTAMP = 1_700_000_000.0


def test_convert_unix_to_datetime():
    as_utc = convert_unix_to_datetime(TIMESTAMP, utc=True)
    assert as_utc == datetime.fromtimestamp(TIMESTAMP, tz=timezone.utc)
    assert as_utc.tzinfo == timezone.utc

    as_local = convert_unix_to_datetime(TIMESTAMP)
    assert as_local.tzinfo is not None
    assert as_local == as_utc
