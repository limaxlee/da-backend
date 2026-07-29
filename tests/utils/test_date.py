from datetime import datetime, timedelta, timezone

import pytest

from data_agent.utils.date import convert_unix_to_datetime


class TestConvertUnixToDatetime:

    def test_returns_datetime_instance(self):
        result = convert_unix_to_datetime(0, utc=True)

        assert isinstance(result, datetime)

    def test_utc_true_returns_utc_aware_datetime(self):
        result = convert_unix_to_datetime(1_700_000_000, utc=True)

        assert result.tzinfo == timezone.utc
        assert result == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_utc_true_epoch_zero(self):
        result = convert_unix_to_datetime(0, utc=True)

        assert result == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_utc_true_keeps_fractional_seconds(self):
        result = convert_unix_to_datetime(1_700_000_000.5, utc=True)

        assert result.microsecond == 500_000

    def test_utc_true_supports_far_future_timestamp(self):
        result = convert_unix_to_datetime(4_102_444_800, utc=True)

        assert result == datetime(2100, 1, 1, tzinfo=timezone.utc)

    def test_defaults_to_local_timezone(self, mocker):
        local_tz = timezone(timedelta(hours=6))
        mock_datetime = mocker.patch("data_agent.utils.date.datetime")
        mock_datetime.now.return_value.astimezone.return_value.tzinfo = local_tz
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp

        result = convert_unix_to_datetime(1_700_000_000)

        mock_datetime.now.assert_called_once_with(timezone.utc)
        mock_datetime.fromtimestamp.assert_called_once_with(1_700_000_000, tz=local_tz)
        assert result.tzinfo == local_tz
        assert result == datetime(2023, 11, 15, 4, 13, 20, tzinfo=local_tz)

    def test_utc_false_explicitly_uses_local_timezone(self, mocker):
        local_tz = timezone(timedelta(hours=-3))
        mock_datetime = mocker.patch("data_agent.utils.date.datetime")
        mock_datetime.now.return_value.astimezone.return_value.tzinfo = local_tz
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp

        result = convert_unix_to_datetime(0, utc=False)

        assert result == datetime(1969, 12, 31, 21, 0, 0, tzinfo=local_tz)

    def test_utc_true_does_not_resolve_local_timezone(self, mocker):
        mock_datetime = mocker.patch("data_agent.utils.date.datetime")
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp

        convert_unix_to_datetime(1_700_000_000, utc=True)

        mock_datetime.now.assert_not_called()
        mock_datetime.fromtimestamp.assert_called_once_with(
            1_700_000_000, tz=timezone.utc
        )

    def test_utc_and_local_describe_the_same_instant(self):
        utc_result = convert_unix_to_datetime(1_700_000_000, utc=True)
        local_result = convert_unix_to_datetime(1_700_000_000)

        assert utc_result == local_result
        assert utc_result.timestamp() == local_result.timestamp()

    @pytest.mark.parametrize("timestamp", [0, 1, 1_000_000, 1_700_000_000.123456])
    def test_roundtrip_preserves_timestamp(self, timestamp):
        result = convert_unix_to_datetime(timestamp, utc=True)

        assert result.timestamp() == pytest.approx(timestamp)

    def test_raises_on_non_numeric_timestamp(self):
        with pytest.raises(TypeError):
            convert_unix_to_datetime("not-a-timestamp", utc=True)
