# -*- coding: utf-8 -*-

import logging
import os
import socket
from datetime import datetime
from dateutil.tz import tzlocal
from queue import Queue
from threading import RLock
import requests

from .consumer import QueueConsumer

# Well-known keyword arguments used by the logging system.
_well_known_logger_kwargs = {"extra", "exc_info", "func", "sinfo"}

# Default global log properties.
_default_global_log_props = {
    "MachineName": socket.gethostname(),
    "ProcessId": os.getpid()
}

# Global properties attached to all log entries.
_global_log_props = _default_global_log_props


def get_global_log_properties(logger_name=None):
    """
    Get the properties to be added to all structured log entries.

    :param logger_name: An optional logger name to be added to the log entry.
    :type logger_name: str
    :return: A copy of the global log properties.
    :rtype: dict
    """

    global_log_properties = {key: value for (key, value) in _global_log_props.items()}

    if logger_name:
        global_log_properties["LoggerName"] = logger_name

    return global_log_properties


def set_global_log_properties(**properties):
    """
    Configure the properties to be added to all structured log entries.

    :param properties: Keyword arguments representing the properties.
    :type properties: dict
    """

    global _global_log_props

    _global_log_props = {key: value for (key, value) in properties.items()}


def reset_global_log_properties():
    """
    Initialize global log properties to their default values.
    """

    global _global_log_props

    _global_log_props = _default_global_log_props


def clear_global_log_properties():
    """
    Remove all global properties.
    """

    global _global_log_props

    _global_log_props = {}


class StructuredLogRecord(logging.LogRecord):
    """
    An extended LogRecord that with custom properties to be logged to Seq.
    """

    def __init__(self, name, level, pathname, lineno, msg, args,
                 exc_info, func=None, sinfo=None, log_props=None, **kwargs):

        """
        Create a new StructuredLogRecord.
        :param name: The name of the logger that produced the log record.
        :param level: The logging level (severity) associated with the logging record.
        :param pathname: The name of the file (if known) where the log entry was created.
        :param lineno: The line number (if known) in the file where the log entry was created.
        :param msg: The log message (or message template).
        :param args: Ordinal message format arguments (if any).
        :param exc_info: Exception information to be included in the log entry.
        :param func: The function (if known) where the log entry was created.
        :param sinfo: Stack trace information (if known) for the log entry.
        :param log_props: Named message format arguments (if any).
        :param kwargs: Keyword (named) message format arguments.
        """

        super().__init__(name, level, pathname, lineno, msg, args, exc_info, func, sinfo, **kwargs)

        self.log_props = log_props or {}

        if self.thread and "ThreadId" not in self.log_props:
            self.log_props["ThreadId"] = self.thread

        if self.threadName and "ThreadName" not in self.log_props:
            self.log_props["ThreadName"] = self.threadName

    def getMessage(self):
        """
        Get a formatted message representing the log record (with arguments replaced by values as appropriate).
        :return: The formatted message.
        """

        if self.args:
            return self.msg % self.args
        elif self.log_props:
            return self.msg.format(**self.log_props)
        else:
            return self.msg


class StructuredLogger(logging.Logger):
    """
    Custom (dummy) logger that understands named log arguments.
    """

    def __init__(self, name, level=logging.NOTSET):
        """
        Create a new StructuredLogger
        :param name: The logger name.
        :param level: The logger minimum level (severity).
        """

        super().__init__(name, level)

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, **kwargs):
        """
        Called by public logger methods to generate a log entry.
        :param level: The level (severity) for the log entry.
        :param msg: The log message or message template.
        :param args: Ordinal arguments for the message format template.
        :param exc_info: Exception information to be included in the log entry.
        :param extra: Extra information to be included in the log entry.
        :param stack_info: Include stack-trace information in the log entry?
        :param kwargs: Keyword arguments (if any) passed to the public logger method that called _log.
        """

        # Slightly hacky:
        #
        # We take keyword arguments provided to public logger methods (except
        # well-known ones used by the logging system itself) and move them
        # into the `extra` argument as a sub-dictionary.

        # Start off with a copy of the global log properties.
        log_props = get_global_log_properties(self.name)

        # Add supplied keyword arguments.
        for prop in kwargs.keys():
            if prop in _well_known_logger_kwargs:
                continue

            log_props[prop] = kwargs[prop]

        extra = extra or {}
        extra['log_props'] = log_props

        super()._log(level, msg, args, exc_info, extra, stack_info)

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        """
        Create a LogRecord.

        :param name: The name of the logger that produced the log record.
        :param level: The logging level (severity) associated with the logging record.
        :param fn: The name of the file (if known) where the log entry was created.
        :param lno: The line number (if known) in the file where the log entry was created.
        :param msg: The log message (or message template).
        :param args: Ordinal message format arguments (if any).
        :param exc_info: Exception information to be included in the log entry.
        :param func: The function (if known) where the log entry was created.
        :param extra: Extra information (if any) to add to the log record.
        :param sinfo: Stack trace information (if known) for the log entry.
        """

        # Do we have named format arguments?
        if extra and 'log_props' in extra:
            return StructuredLogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo, extra['log_props'])

        return super().makeRecord(name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)


class StructuredRootLogger(logging.RootLogger):
    """
    Custom root logger that understands named log arguments.
    """

    def __init__(self, level=logging.NOTSET):
        """
        Create a `StructuredRootLogger`.
        """

        super().__init__(level)

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, **kwargs):
        """
        Called by public logger methods to generate a log entry.

        :param level: The level (severity) for the log entry.
        :param msg: The log message or message template.
        :param args: Ordinal arguments for the message format template.
        :param exc_info: Exception information to be included in the log entry.
        :param extra: Extra information to be included in the log entry.
        :param stack_info: Include stack-trace information in the log entry?
        :param kwargs: Keyword arguments (if any) passed to the public logger method that called _log.
        """

        # Slightly hacky:
        #
        # We take keyword arguments provided to public logger methods (except
        # well-known ones used by the logging system itself) and move them
        # into the `extra` argument as a sub-dictionary.
        log_props = get_global_log_properties(self.name)
        for prop in kwargs.keys():
            if prop in _well_known_logger_kwargs:
                continue

            log_props[prop] = kwargs[prop]

        extra = extra or {}
        extra['log_props'] = log_props

        super()._log(level, msg, args, exc_info, extra, stack_info)

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        """
        Create a `LogRecord`.

        :param name: The name of the logger that produced the log record.
        :param level: The logging level (severity) associated with the logging record.
        :param fn: The name of the file (if known) where the log entry was created.
        :param lno: The line number (if known) in the file where the log entry was created.
        :param msg: The log message (or message template).
        :param args: Ordinal message format arguments (if any).
        :param exc_info: Exception information to be included in the log entry.
        :param func: The function (if known) where the log entry was created.
        :param extra: Extra information (if any) to add to the log record.
        :param sinfo: Stack trace information (if known) for the log entry.
        """

        # Do we have named format arguments?
        if extra and 'log_props' in extra:
            return StructuredLogRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo, extra['log_props'])

        return super().makeRecord(name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)


class ConsoleStructuredLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        msg = self.format(record)

        print(msg)
        if hasattr(record, 'kwargs'):
            print("\tLog entry properties: {}".format(repr(record.kwargs)))


class SeqLogHandler(logging.Handler):
    """
    Log handler that posts to Seq.
    """

    def __init__(self, server_url, api_key=None, batch_size=10, auto_flush_timeout=None):
        """
        Create a new `SeqLogHandler`.

        :param server_url: The Seq server URL.
        :param api_key: The Seq API key (if any).
        :param batch_size: The number of messages to batch up before posting to Seq.
        :param auto_flush_timeout: If specified, the time (in seconds) before
                                   the current batch is automatically flushed.
        """

        super().__init__()

        self.publish_lock = RLock()

        self.server_url = server_url
        if not self.server_url.endswith("/"):
            self.server_url += "/"
        self.server_url += "api/events/raw"

        self.session = requests.Session()
        if api_key:
            self.session.headers["X-Seq-ApiKey"] = api_key

        self.log_queue = Queue()
        self.consumer = QueueConsumer(
            name="SeqLogHandler",
            queue=self.log_queue,
            callback=self.publish_log_batch,
            batch_size=batch_size,
            auto_flush_timeout=auto_flush_timeout
        )
        self.consumer.start()

    def flush(self):
        try:
            self.consumer.flush()
        finally:
            super().flush()

    def emit(self, record):
        """
        Emit a log record.

        :param record: The LogRecord.
        """

        self.log_queue.put(record)

    def close(self):
        """
        Close the log handler.
        """

        try:
            self.consumer.stop()
            self.session.close()
        finally:
            super().close()

    def publish_log_batch(self, batch):
        """
        Publish a batch of log records.

        :param batch: A list representing the batch.
        """

        if len(batch) == 0:
            return

        request_body = {
            "Events": [
                _build_event_data(record) for record in batch
            ]
        }

        self.publish_lock.acquire()
        try:
            response = self.session.post(self.server_url, json=request_body)
            response.raise_for_status()
        except requests.RequestException:
            # Only notify for the first record in the batch, or we'll be generating too much noise.
            self.handleError(batch[0])
        finally:
            self.publish_lock.release()


def _build_event_data(record):
    """
    Build an event data dictionary from the specified log record for submission to Seq.

    :param record: The LogRecord.
    :type record: StructuredLogRecord
    :return: A dictionary containing event data representing the log record.
    :rtype: dict
    """

    if record.args:
        # Standard (unnamed) format arguments (use 0-base index as property name).
        log_props_shim = get_global_log_properties(record.name)
        for (arg_index, arg) in enumerate(record.args or []):
            log_props_shim[str(arg_index)] = arg

        event_data = {
            "Timestamp": _get_local_timestamp(record),
            "Level": logging.getLevelName(record.levelno),
            "MessageTemplate": record.getMessage(),
            "Properties": log_props_shim
        }
    elif isinstance(record, StructuredLogRecord):
        # Named format arguments (and, therefore, log event properties).
        event_data = {
            "Timestamp": _get_local_timestamp(record),
            "Level": logging.getLevelName(record.levelno),
            "MessageTemplate": record.msg,
            "Properties": record.log_props
        }
    else:
        # No format arguments; interpret message as-is.
        event_data = {
            "Timestamp": _get_local_timestamp(record),
            "Level": logging.getLevelName(record.levelno),
            "MessageTemplate": record.getMessage(),
            "Properties": _global_log_props
        }

    return event_data


def _get_local_timestamp(record):
    """
    Get the record's UTC timestamp as an ISO-formatted date / time string.

    :param record: The LogRecord.
    :type record: StructuredLogRecord
    :return: The ISO-formatted date / time string.
    :rtype: str
    """

    timestamp = datetime.fromtimestamp(
        timestamp=record.created,
        tz=tzlocal()
    )

    return timestamp.isoformat(sep=' ')
