from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Generic, TypeVar

from pydantic import BaseModel

NormalizedRecord = TypeVar("NormalizedRecord", bound=BaseModel)


class SourceAdapter(ABC, Generic[NormalizedRecord]):
    """Each adapter owns extraction and maps records to internal schemas."""

    @abstractmethod
    def extract(self) -> Iterable[object]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: object) -> NormalizedRecord:
        raise NotImplementedError

    def records(self) -> Iterable[NormalizedRecord]:
        for raw in self.extract():
            yield self.normalize(raw)
