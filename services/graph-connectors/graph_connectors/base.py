from abc import ABC, abstractmethod

from shared_schemas.config import AppSettings


class ConnectorBase(ABC):
    connector_name: str

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @abstractmethod
    def describe_scope(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def sync_interval_seconds(self) -> int:
        raise NotImplementedError
