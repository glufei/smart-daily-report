class DailyReportError(Exception):
    """Base class for safe, user-facing application errors."""


class ConfigError(DailyReportError):
    pass


class CollectorError(DailyReportError):
    pass


class GeneratorError(DailyReportError):
    pass


class NotifierError(DailyReportError):
    pass
