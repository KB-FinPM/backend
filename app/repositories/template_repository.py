# EN: Repository for artifact template lookup.
# KO: 산출물 템플릿 조회를 담당하는 Repository입니다.

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import TemplateModel


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_template(
        self,
        *,
        template_id: str,
        template_version: Optional[str] = None,
    ) -> Optional[TemplateModel]:
        statement = select(TemplateModel).where(TemplateModel.template_id == template_id)
        if template_version is not None:
            statement = statement.where(
                TemplateModel.template_version == template_version
            )
        else:
            statement = statement.order_by(TemplateModel.created_at.desc())

        result = await self.session.execute(statement)
        return result.scalars().first()
