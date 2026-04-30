from pydantic import BaseModel, Field


class PostMarketSnapshotResponse(BaseModel):
    trade_date: str
    snapshot_version: str
    payload: dict = Field(default_factory=dict)


class StrongWatchResponse(BaseModel):
    trade_date: str
    stocks: list[dict] = Field(default_factory=list)


class W2SCandidatesResponse(BaseModel):
    trade_date: str
    candidates: list[dict] = Field(default_factory=list)
