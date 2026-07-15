from dataclasses import asdict, is_dataclass
from typing import Any, Generic, TypeVar

from src.features.membership.models.entities import MembershipModel
from src.features.membership.repositories.base import BaseRepository


ModelT = TypeVar("ModelT", bound=MembershipModel)


class BaseService(Generic[ModelT]):
    repository: BaseRepository[ModelT]

    def __init__(self, repository: BaseRepository[ModelT]):
        self.repository = repository

    def get_required(self, entity_id: str) -> ModelT:
        from src.features.membership.core.exceptions import ResourceNotFoundError

        entity = self.repository.get_by_id(entity_id)
        if entity is None:
            raise ResourceNotFoundError(details={"id": entity_id})
        return entity

    def to_response_dict(self, entity: Any) -> dict[str, Any]:
        if is_dataclass(entity):
            return asdict(entity)
        if hasattr(entity, "to_dict"):
            return entity.to_dict()
        return dict(entity)
