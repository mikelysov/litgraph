from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from src.config import PAPER_INDEX_PATH
from src.models import PaperState
from src.store.models import Base, Paper, PaperHistory


class PaperIndex:
    def __init__(self, db_url: str | None = None, db_path: Path = PAPER_INDEX_PATH):
        if db_url is not None:
            self.engine = create_engine(
                db_url,
                future=True,
                pool_pre_ping=True,
                pool_recycle=1800,  # recycle stale connections every 30 min
            )
        else:
            self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        # Create the tables if they don't exist
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

    def get(self, paper_id: str) -> PaperState | None:
        """Get the state of a paper by its ID."""
        with self.Session() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                return None
            return PaperState.model_validate(paper)

    def set(self, paper_state: PaperState) -> None:
        """Set the state of a paper."""
        now = paper_state.last_seen or datetime.now()
        with self.Session() as session:
            paper_instance = session.get(Paper, paper_state.id)
            # Create a new Paper instance if it doesn't exist
            if paper_instance is None:
                paper_instance = Paper(
                    id=paper_state.id,
                    status=paper_state.status,
                    in_graph=paper_state.in_graph,
                    last_seen=now,
                )
                session.add(paper_instance)
            # Otherwise, update the existing one
            else:
                paper_instance.status = paper_state.status  # type: ignore
                paper_instance.in_graph = paper_state.in_graph  # type: ignore
                paper_instance.last_seen = now  # type: ignore

            # Use an upsert for PaperHistory to avoid UNIQUE constraint violations
            stmt = (
                (
                    pg_insert
                    if self.engine.url.get_backend_name() == "postgresql"
                    else sqlite_insert
                )(PaperHistory)
                .values(id=paper_state.id, state=paper_state.status)
                .on_conflict_do_nothing(index_elements=["id"])
            )

            session.execute(stmt)
            session.commit()

    def set_many(self, states: list[PaperState]) -> None:
        """Set the state of multiple papers."""
        ids = [s.id for s in states]
        now = datetime.now()
        with self.Session() as session:
            existing_papers = session.query(Paper).filter(Paper.id.in_(ids)).all()
            existing_map = {p.id: p for p in existing_papers}

            for s in states:
                obj = existing_map.get(s.id)
                if obj is None:
                    obj = Paper(
                        id=s.id,
                        status=s.status,
                        in_graph=s.in_graph,
                        last_seen=now,
                    )
                    session.add(obj)
                else:
                    obj.status = s.status  # type: ignore
                    obj.in_graph = s.in_graph  # type: ignore
                    obj.last_seen = now  # type: ignore

                stmt = (
                    (
                        pg_insert
                        if self.engine.url.get_backend_name() == "postgresql"
                        else sqlite_insert
                    )(PaperHistory)
                    .values(id=s.id, state=s.status)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                session.execute(stmt)

            session.commit()

    def is_healthy(self) -> bool:
        """Perform a health check on the paper index."""
        try:
            with self.Session() as session:
                # Check if we can query the Paper table
                session.query(Paper).first()
            return True
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    def __del__(self):
        """Close the database connection when the instance is deleted."""
        self.engine.dispose()
