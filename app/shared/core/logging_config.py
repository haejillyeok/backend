import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_RETENTION_DAYS = 14
DEFAULT_LOG_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
DEFAULT_LOG_CLEANUP_INTERVAL_SECONDS = 60
FILE_LOGGER_NAMES = ("uvicorn", "uvicorn.access")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LogFileSettings:
    enabled: bool = True
    directory: Path = Path(DEFAULT_LOG_DIR)
    retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    max_total_bytes: int = DEFAULT_LOG_MAX_TOTAL_BYTES
    cleanup_interval_seconds: int = DEFAULT_LOG_CLEANUP_INTERVAL_SECONDS

    @classmethod
    def from_environment(cls) -> "LogFileSettings":
        """환경변수에서 파일 로그 저장과 정리 기준을 읽어옵니다.

        주요 입력은 프로세스 환경변수이며, 반환값은 로깅 설정에서 사용할 immutable 설정입니다.
        부작용은 없고 잘못된 숫자 값은 기본값으로 되돌립니다.
        """
        return cls(
            enabled=_read_bool_env("LOG_FILE_ENABLED", default=True),
            directory=Path(os.getenv("LOG_DIR", DEFAULT_LOG_DIR)),
            retention_days=_read_int_env("LOG_RETENTION_DAYS", DEFAULT_LOG_RETENTION_DAYS),
            max_total_bytes=_read_int_env("LOG_MAX_TOTAL_BYTES", DEFAULT_LOG_MAX_TOTAL_BYTES),
            cleanup_interval_seconds=_read_int_env(
                "LOG_CLEANUP_INTERVAL_SECONDS",
                DEFAULT_LOG_CLEANUP_INTERVAL_SECONDS,
            ),
        )


class ManagedTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename: Path,
        settings: LogFileSettings,
    ) -> None:
        """시간 회전과 주기적 파일 정리를 함께 수행하는 로그 handler입니다.

        주요 입력은 로그 파일 경로와 파일 로그 설정입니다. 반환값은 없고, 로그를 쓸 때 주기적으로
        오래된 로그 파일을 삭제하는 부작용이 있습니다.
        """
        super().__init__(
            filename,
            when="midnight",
            interval=1,
            backupCount=settings.retention_days,
            encoding="utf-8",
        )
        self._settings = settings
        self._log_path = Path(filename)
        self._next_cleanup_at = time.monotonic() + settings.cleanup_interval_seconds

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self._cleanup_if_due()

    def doRollover(self) -> None:
        super().doRollover()
        cleanup_log_files(
            self._settings.directory,
            self._settings.retention_days,
            self._settings.max_total_bytes,
            protected_paths={self._log_path},
        )

    def _cleanup_if_due(self) -> None:
        now = time.monotonic()
        if now < self._next_cleanup_at:
            return
        self._next_cleanup_at = now + self._settings.cleanup_interval_seconds
        cleanup_log_files(
            self._settings.directory,
            self._settings.retention_days,
            self._settings.max_total_bytes,
            protected_paths={self._log_path},
        )


def configure_logging(app_name: str, environment: str | None = None) -> None:
    """앱 공통 로깅을 stdout과 rotating file handler에 설정합니다.

    주요 입력은 앱 이름과 실행 환경이며, 반환값은 없습니다. 루트 logger handler와 log record
    factory를 갱신하고, 파일 로그가 켜져 있으면 `LOG_DIR`에 앱별 로그 파일을 쓰는 부작용이 있습니다.
    """
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

    log_file_settings = LogFileSettings.from_environment()
    if not log_file_settings.enabled:
        logger.info("File logging disabled log_dir=%s", log_file_settings.directory)
        return

    try:
        add_file_log_handler(root_logger, app_name, log_level, formatter, log_file_settings)
    except OSError:
        logger.exception(
            "File logging setup failed path=%s. Continuing with stdout logging only.",
            log_file_settings.directory / f"{app_name}.log",
        )


def add_file_log_handler(
    root_logger: logging.Logger,
    app_name: str,
    log_level: int,
    formatter: logging.Formatter,
    settings: LogFileSettings,
) -> None:
    """루트 logger에 앱별 파일 로그 handler를 추가합니다.

    주요 입력은 root logger, 앱 이름, formatter, 파일 로그 설정입니다. 반환값은 없고, 로그
    디렉터리를 만들고 기존 handler를 교체한 뒤 오래된 로그 파일을 정리하는 부작용이 있습니다.
    """
    settings.directory.mkdir(parents=True, exist_ok=True)
    log_path = settings.directory / f"{app_name}.log"
    file_loggers = [logging.getLogger(name) for name in FILE_LOGGER_NAMES]

    remove_project_file_handlers(root_logger, *file_loggers)

    cleanup_log_files(settings.directory, settings.retention_days, settings.max_total_bytes)

    file_handler = ManagedTimedRotatingFileHandler(
        log_path,
        settings=settings,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler._haejillyeok_file_handler = True
    file_handler._haejillyeok_log_path = log_path
    root_logger.addHandler(file_handler)
    for file_logger in file_loggers:
        file_logger.addHandler(file_handler)
        file_logger.propagate = False

    logger.info(
        "File logging configured path=%s retention_days=%s max_total_bytes=%s",
        log_path,
        settings.retention_days,
        settings.max_total_bytes,
    )


def remove_project_file_handlers(*loggers: logging.Logger) -> None:
    """프로젝트가 추가한 파일 handler를 logger들에서 제거합니다.

    주요 입력은 logger 목록이며, 반환값은 없습니다. 같은 handler가 여러 logger에 붙어 있어도 한 번만
    close해 handler 교체 중 파일 descriptor가 남지 않도록 합니다.
    """
    closed_handler_ids: set[int] = set()
    for logger in loggers:
        for handler in list(logger.handlers):
            if not getattr(handler, "_haejillyeok_file_handler", False):
                continue

            logger.removeHandler(handler)
            handler_id = id(handler)
            if handler_id in closed_handler_ids:
                continue

            handler.close()
            closed_handler_ids.add(handler_id)


def cleanup_log_files(
    log_dir: Path,
    retention_days: int,
    max_total_bytes: int,
    protected_paths: set[Path] | None = None,
) -> None:
    """보존 기간과 전체 용량 기준에 맞춰 오래된 로그 파일을 삭제합니다.

    주요 입력은 로그 디렉터리, 보존 일수, 허용 전체 byte 수입니다. 반환값은 없고,
    `*.log*` 파일 중 기준을 넘긴 파일을 삭제하는 부작용이 있습니다.
    """
    if retention_days < 1 or max_total_bytes < 1 or not log_dir.exists():
        return

    protected_paths = {path.resolve() for path in protected_paths or set()}
    now = datetime.now(UTC)
    retention_cutoff = now - timedelta(days=retention_days)
    log_files = sorted(
        (path for path in log_dir.glob("*.log*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    kept_files: list[Path] = []
    for path in log_files:
        if path.resolve() in protected_paths:
            kept_files.append(path)
            continue

        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified_at < retention_cutoff:
            _delete_log_file(path)
        else:
            kept_files.append(path)

    total_bytes = sum(path.stat().st_size for path in kept_files if path.exists())
    for path in sorted(kept_files, key=lambda target: target.stat().st_mtime):
        if total_bytes <= max_total_bytes:
            break
        if path.resolve() in protected_paths:
            continue
        file_size = path.stat().st_size
        if _delete_log_file(path):
            total_bytes -= file_size


def _delete_log_file(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("Failed to delete log file: %s", path)
        return False
    return True


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
