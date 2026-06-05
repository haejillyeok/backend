import logging


def configure_logging(app_name: str, environment: str | None = None) -> None:
    log_level = logging.INFO if environment == "prod" else logging.DEBUG
    log_format = "%(asctime)s %(levelname)s [%(app_name)s] [%(name)s] %(message)s"
    log_record_factory = logging.getLogRecordFactory()

    def add_app_name(*args, **kwargs):
        record = log_record_factory(*args, **kwargs)
        record.app_name = app_name
        return record

    logging.setLogRecordFactory(add_app_name)

    logging.basicConfig(
        level=log_level,
        format=log_format,
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(log_format)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
