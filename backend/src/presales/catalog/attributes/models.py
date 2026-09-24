from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from presales.storage import Base, identifier


class ProductAttributes(Base):
    __tablename__ = "product_attributes"
    product_id: Mapped[str] = mapped_column(ForeignKey("product_records.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class AttributeRevision(Base):
    __tablename__ = "attribute_revisions"
    __table_args__ = (UniqueConstraint("product_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    product_id: Mapped[str] = mapped_column(ForeignKey("product_records.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
