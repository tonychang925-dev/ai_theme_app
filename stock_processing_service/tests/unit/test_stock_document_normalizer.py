"""StockDocumentNormalizer contract tests."""

from __future__ import annotations

from stock_processing_service.application.services.review_document.stock_document_normalizer import (
    StockDocumentNormalizer,
)


def test_stock_document_normalizer_maps_strong_stock_row_to_contract() -> None:
    stock = StockDocumentNormalizer().normalize(
        {
            "stock_code": "002747.SZ",
            "stock_name": "埃斯顿",
            "subject_key": "9014636",
            "theme_name": "人形机器人",
            "role": "sub_dragon",
            "board_height": 2,
        }
    )

    assert stock == {
        "code": "002747.SZ",
        "name": "埃斯顿",
        "themes": [{"name": "人形机器人", "key": "9014636"}],
        "role": "sub_dragon",
        "height": 2,
    }


def test_stock_document_normalizer_removes_independent_theme_marker() -> None:
    stock = StockDocumentNormalizer().normalize(
        {
            "stock_code": "000566.SZ",
            "stock_name": "000566.SZ",
            "subject_key": "__independent__",
            "theme_name": "__independent__",
            "role": "unknown",
        }
    )

    assert stock == {
        "code": "000566.SZ",
        "name": None,
        "themes": [],
        "role": "unknown",
        "height": None,
        "quality": "DEGRADED",
    }


def test_stock_document_normalizer_keeps_existing_theme_array_shape() -> None:
    stock = StockDocumentNormalizer().normalize(
        {
            "stock_code": "002747.SZ",
            "stock_name": "埃斯顿",
            "themes": [{"name": "人形机器人", "subject_key": "9014636"}],
        }
    )

    assert stock["themes"] == [{"name": "人形机器人", "key": "9014636"}]


def test_stock_document_normalizer_filters_independent_theme_array_item() -> None:
    stock = StockDocumentNormalizer().normalize(
        {
            "stock_code": "000566.SZ",
            "stock_name": "示例股份",
            "themes": [{"name": "__independent__", "subject_key": "__independent__"}],
        }
    )

    assert stock["themes"] == []
    assert stock["quality"] == "DEGRADED"
