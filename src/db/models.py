from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GroupUser(Base):
    __tablename__ = "group_users"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class GroupQueueState(Base):
    __tablename__ = "group_queue_state"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
