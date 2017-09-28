#
#  Copyright 2017 TWO SIGMA OPEN SOURCE, LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import collections.abc

import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql.readwriter import DataFrameReader, DataFrameWriter

from . import java
from . import utils


class TSDataFrameReader(object):
    '''Interface used to load a :class:`.TimeSeriesDataFrame`

    This reader has builder methods that enable setting parameter values
    before calling a reader method.  Multiple calls to the same builder
    method will take the last values set in the call chain.

    Example usage:

    >>> df = (flintContext.read
    ...       .range('20170101', '20170201', timezone='America/New_York')
    ...       .option('partitionGranularity', '1m')
    ...       .option('columns', ['x', 'y', 'z'])
    ...       .uri('...'))
    '''

    def __init__(self, flintContext):
        self._flintContext = flintContext
        self._sc = self._flintContext._sc
        self._sqlContext = self._flintContext._sqlContext
        self._jpkg = java.Packages(self._sc)
        self._builder = self._jpkg.read.builder(utils.jsc(self._sc))
        self._parameters = self._builder.parameters()

    def option(self, key, value):
        """
        Set a key-value option for the data reader.

        Refer to the documentation for data reader, e.g.,
        :meth:`.TSDataFrameReader.uri`,
        :meth:`.TSDataFrameReader.parquet`, for a list of its supported
        options.

        Example usage:

            >>> (flintContext.read
            ...  .range('2017-01-01', '2017-02-01')
            ...  .option('numPartitions', 4)
            ...  .option('columns', ['x', 'y', 'z'])
            ...  .uri('...'))

        :param str key: The string key, e.g., "numPartitions",
            "partitionGranularity"
        :param value: The value for the option.
            Any value that is not a string will be converted using
            ``str(..)``. For keys that support multiple values,
            separate values with commas ','. List are converted into
            a string where the values are comma-separated.
        :return: The :class:`.TSDataFrameReader`
        :rtype: TSDataFrameReader
        """

        # If the value is a list, we concatenate the values separated
        # by a comma
        if (isinstance(value, collections.abc.Iterable)
            and not isinstance(value, str)):
            value = ','.join([str(v) for v in value])

        self._builder.option(key, str(value))
        return self

    def options(self, **options):
        """
        Set one or more options using kwarg syntax. Keys with a value of
        None are ignored.

        Example usage:
            >>> (flintContext.read
            ...  .range('2017-01-01', '2017-02-01')
            ...  .options(numPartitions=4, columns=['x', 'y', 'z'])
            ...  .uri('...'))

        :return: The :class:`.TSDataFrameReader`
        :rtype: TSDataFrameReader
        """
        for k, v in options.items():
            if v is not None:
                self.option(k, v)
        return self

    def range(self, begin=None, end=None, timezone='UTC'):
        """
        Builder method to set the begin and end date range for the
        reader. Dates specified without a time have their time set to
        midnight in the timezone specified in the ``tz`` parameter.
        Default: UTC.

        Supported date specifications for ``begin`` and ``end``:

            - A string or object supported by :func:`pandas.to_datetime`
              e.g., "2017-01-01", "20170101", "20170101 10:00"
              "2017-07-14T10:00:00-05:00"
            - A YYYYMMDD integer, e.g., 20170714
            - A :class:`datetime.datetime`
            - A :class:`pandas.Timestamp`

        .. note:: The time range is ``begin``-inclusive and
            `end`-exclusive.

            ``end`` is exclusive, taking the last nanoseconds before
            the specified datetime. For example, if ``end`` is
            "2017-02-01" then the reader will read data up to and
            including "2017-01-31 23:59:59.999999999" but excluding
            "2017-02-01 00:00".

        Examples for specifying a ``begin`` time of "2017-01-01 00:00 UTC"
        inclusive and ``end`` time of "2017-02-01 00:00 UTC" exclusive:

            >>> flintContext.read.range('2017-01-01', '2017-02-01').uri('...')
            ...
            >>> flintContext.read.range('20161231 19:00',
            ...                         '20170131 19:00',
            ...                         'America/New_York').uri('...')
            ...
            >>> flintContext.read.range(20170101, 20170201).uri('...')
            ...
            >>> from datetime import datetime
            ... flintContext.read.range(datetime(2017, 1, 1, 0, 0),
            ...                         datetime(2017, 2, 1, 0, 0)).uri('...')

        :param begin: The inclusive begin date of the date range.
        :type begin: str, int, :class:`pandas.Timestamp`
        :param end: The exclusive end date of date range.
        :type end: str, int, :class:`pandas.Timestamp`
        :param str tz: the timezone to localize the begin and end dates
            if the provided dates are timezone-naive. Default: UTC.
        :return: The :class:`.TSDataFrameReader`
        :see: :func:`pandas.to_datetime` for examples of supported
            formats for strings
        :rtype: TSDataFrameReader
        """
        begin_ns = _to_timestamp(begin, timezone).value if begin else None
        end_ns = _to_timestamp(end, timezone).value if end else None
        self._builder.range(begin_ns, end_ns)
        return self

    def pandas(self, df, schema=None, *,
               is_sorted=True,
               time_column=None,
               unit=None):
        '''Creates a :class:`.TimeSeriesDataFrame` from an existing
        :class:`pandas.DataFrame`. The :class:`pandas.DataFrame` must be sorted on
        time column, otherwise user must specify ``is_sorted=False``.

        **Supported options:**

        timeUnit (optional)
            Time unit of the time column. Default: "ns"
        timeColumn (optional)
            Name of the time column. Default: "time"

        :param pandas.DataFrame df: the :class:`pandas.DataFrame` to convert
        :param bool is_sorted: Default True. Whether the input data is already
            sorted (if already sorted, the conversion will be faster)
        :param str time_column: **Deprecated**. Column name used to sort rows
            Default: "time".
            Use ``option("timeColumn", column)`` instead.
        :param str unit: **Deprecated**. Unit of time_column, can be (s,ms,us,ns)
            Default: "ns".
            Use ``option("timeUnit", unit)`` instead.
        :return: a new :class:`TimeSeriesDataFrame` containing the
            data in ``df``
        '''
        from .dataframe import TimeSeriesDataFrame

        self._reconcile_reader_args(
            timeColumn=time_column,
            timeUnit=unit
        )

        return TimeSeriesDataFrame._from_pandas(
            df, schema, self._flintContext._sqlContext,
            time_column=self._parameters.timeColumn(),
            is_sorted=is_sorted,
            unit=self._parameters.timeUnitString())

    def _df_between(self, df, begin, end, time_column, junit):
        """Filter a Python dataframe to contain data between begin (inclusive) and end (exclusive)

        :return: :class:`pyspark.sql.DataFrame`
        """
        jdf = df._jdf
        new_jdf = self._jpkg.TimeSeriesRDD.DFBetween(jdf, begin, end, junit, time_column)

        return DataFrame(new_jdf, self._sqlContext)

    def dataframe(self, df, begin=None, end=None, *,
                  timezone='UTC',
                  is_sorted=True,
                  time_column=None,
                  unit=None):
        """Creates a :class:`TimeSeriesDataFrame` from an existing
        :class:`pyspark.sql.DataFrame`. The :class:`pyspark.sql.DataFrame` must be
        sorted on time column, otherwise user must specify
        is_sorted=False.

        **Supported options:**

        range (optional)
            Set the inclusive-begin and exclusive-end time range. Begin
            and end are optional and either begin, end, or both begin
            and end can be omitted. If omitted, no boundary on time
            range will be set.
            Specified using :meth:`.TSDataFrameReader.range`.
        timeUnit (optional)
            Time unit of the time column. Default: "ns"
        timeColumn (optional)
            Column in parquet table that specifies time. Default: "time"

        :param pyspark.sql.DataFrame df: the :class:`pyspark.sql.DataFrame`
            to convert
        :param str begin: **Deprecated**. Inclusive. Supports most
            common date formats.
            Use ``range(begin, end)`` instead.
        :param str end: **Deprecated**. Exclusive. Supports most
            common date formats.
            Use ``range(begin, end)`` instead.
        :param str timezone: **Deprecated**. Timezone of the input time
            range. Only used if ``begin`` and ``end`` parameter are set.
            Default: 'UTC'.
            Use ``range(begin, end, timezone="...")``
            instead.
        :param bool is_sorted: Default True. Whether the input data is
            already sorted (if already sorted, the conversion will be
            faster)
        :param str time_column: **Deprecated**. Column name used to sort
            rows. Default: "time".
            Use ``option("timeColumn", column)`` instead.
        :param str unit: **Deprecated**. Unit of time_column, can be
            (s,ms,us,ns). Default: "ns".
            Use ``option("timeUnit", unit)`` instead.
        :return: a new :class:`TimeSeriesDataFrame` containing the
            data in ``df``
        """
        from .dataframe import TimeSeriesDataFrame
        self._reconcile_reader_args(
            begin=begin,
            end=end,
            timezone=timezone,
            timeColumn=time_column,
            timeUnit=unit
        )

        begin = self._parameters.range().beginFlintString()
        end = self._parameters.range().endFlintString()
        time_column = self._parameters.timeColumn()
        jtimeunit = self._parameters.timeUnit()

        if begin or end:
            df = self._df_between(df, begin, end, time_column, jtimeunit)

        return TimeSeriesDataFrame._from_df(
            df,
            time_column=time_column,
            is_sorted=is_sorted,
            unit=self._parameters.timeUnitString())

    def parquet(self, *paths):
        """
        Create a :class:`TimeSeriesDataFrame` from one or more paths
        containing parquet files.

        **Supported options:**

        range (optional)
            Set the inclusive-begin and exclusive-end time range. Begin
            and end are optional and either begin, end, or both begin
            and end can be omitted. If omitted, no boundary on time
            range will be set.
            Specified using :meth:`.TSDataFrameReader.range`.
        timeUnit (optional)
            Time unit of the time column. Default: "ns"
        timeColumn (optional)
            Column in parquet table that specifies time. Default: "time"
        columns* (optional)
            A subset of columns to retain from the parquet table.
            Specifying a subset of columns can greatly improve
            performance by 10x compared to reading all columns in a set
            of parquet files. Default: all columns are retained.

        :param str paths: one or more paths / URIs containing parquet files
        :return: a new :class:`TimeSeriesDataFrame`
        :rtype: TimeSeriesDataFrame
        """
        df = self._sqlContext.read.parquet(*paths)
        return self.dataframe(df)

    def _reconcile_reader_args(self, begin=None, end=None, timezone='UTC',
                               numPartitions=None,
                               partitionGranularity=None,
                               columns=None,
                               timeUnit=None,
                               timeColumn=None):
        """
        Called by reader methods to reconcile any parameters passed as arguments
        to the reader method with parameters passed via builder methods.

        :see: :meth:`.TSDataFrameReader.uri`
        :see: :meth:`.TSDataFrameReader.alf`
        :see: :meth:`.TSDataFrameReader.dataframe`
        :see: :meth:`.TSDataFrameReader.pandas`

        :param check_range_is_set: if ``True``, raises a ``ValueError`` if
            ``begin`` or ``end`` are None after reconciling reader and
            builder parameters.
        :return: A new instance of :class:`.TSDataFrameReader` with any reader
            arguments merged with any builder parameters
        :rtype: :class:`.TSDataFrameReader`
        """
        if begin or end:
            self.range(begin, end, timezone)

        self.options(
            numPartitions=numPartitions,
            partitionGranularity=partitionGranularity,
            columns=columns,
            timeUnit=timeUnit,
            timeColumn=timeColumn
        )
        return self

    @property
    def _extra_options(self):
        """
        :return: a dict containing string key-value pairs
        """
        return self._parameters.extraOptionsAsJavaMap()


class TSDataFrameWriter(DataFrameWriter):
    def __init__(self, df):
        super().__init__(df)
        self._jpkg = java.Packages(self._df._sc)


def _to_timestamp(value, tz):
    """
    Constructs a :class:`pandas.Timestamp` given a parseable value and a
    timezone.
    """
    if value is None:
        return None

    # Handle integers specified as YYYYMMDD
    if isinstance(value, int):
        value = str(value)

    # Convert a Timestamp-compatible value and localize it to the `tz`
    # timezone
    return pd.Timestamp(value, tz=tz)
