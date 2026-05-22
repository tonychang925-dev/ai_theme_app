from pathlib import Path


_APP_SOURCE = Path(__file__).resolve().parents[2] / "app.py"
_OLD_COLLECTION_MANAGER = Path(__file__).resolve().parents[2] / "services" / "collection_job_manager.py"


def test_bff_collection_routes_proxy_sps_instead_of_old_job_manager() -> None:
    source = _APP_SOURCE.read_text(encoding="utf-8")

    assert "from frontend_bff.services.collection_job_manager import CollectionJobManager" not in source
    assert "collection_job_manager = CollectionJobManager()" not in source
    assert "/api/v1/collection/availability" in source
    assert "/api/v1/collection/start" in source
    assert "/api/v1/collection/status" in source
    assert "/api/v1/collection/cancel" in source
    assert "/api/v1/collection/continue" in source
    assert not _OLD_COLLECTION_MANAGER.exists()
