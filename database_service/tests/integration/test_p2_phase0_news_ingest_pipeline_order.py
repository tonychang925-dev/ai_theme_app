import pytest


pytestmark = pytest.mark.skip(reason="P2.phase0 ingest pipeline order not completed yet")


def test_news_stream_handler_precedes_news_stream_processor():
    pass

