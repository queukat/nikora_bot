import sys
import types
import unittest
from datetime import timezone

if "httpx" not in sys.modules:
    sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=object)
if "dateutil" not in sys.modules:
    sys.modules["dateutil"] = types.SimpleNamespace(tz=types.SimpleNamespace(UTC=timezone.utc))

from app.nikora_api import EuroproductApi


SAMPLE_HTML = """
<div class="row product-grid position-relative js-preloader-container">
    <div class="col-sm-4 col-md-6 col-lg-4">
        <div class="product-grid-item js-product-item">
            <div class="img-wrap">
                <div class="sale-badge">
                    <img src="/Content/Images/icons/tag.svg" alt="tag icon">
                    <span>-26%</span>
                </div>
                <figure class="embed-responsive embed-responsive-1by1">
                    <a href="https://europroduct.ge/products/product/00D73FE13A" target="_blank">
                        <img class="embed-responsive-item" src="https://images.europroduct.ge/prod/00d73fe13a/8001841618869.jpg?w=500" alt="ჭურჭლის ჟელე 'ფეირი' ვაშლი 1ლ">
                    </a>
                </figure>
                <a href="#" class="btn btn-primary add-to-cart-btn js-add-to-cart" data-id="00D73FE13A">
                    <span>დამატება</span>
                </a>
            </div>
            <div class="info-wrap">
                <h2 class="product-name">
                    <a href="https://europroduct.ge/products/product/00D73FE13A">ჭურჭლის ჟელე 'ფეირი' ვაშლი 1ლ</a>
                </h2>
                <p class="product-description"></p>
                <span class="product-price">
                    <span class="new">8,59 ₾</span>
                    <span class="old">11,55 ₾</span>
                </span>
            </div>
        </div>
    </div>
</div>
<ul class="pagination">
    <li><a href="https://europroduct.ge/products/page-2?Promo=1">2</a></li>
    <li><a href="https://europroduct.ge/products/page-40?Promo=1">40</a></li>
</ul>
"""


class EuroproductParserTests(unittest.TestCase):
    def test_parse_promo_page(self) -> None:
        deals, page_count = EuroproductApi.parse_promo_page(SAMPLE_HTML, "https://europroduct.ge/")

        self.assertEqual(page_count, 40)
        self.assertEqual(len(deals), 1)

        deal = deals[0]
        self.assertEqual(deal.id, "europroduct:00D73FE13A")
        self.assertEqual(deal.raw_id, "00D73FE13A")
        self.assertEqual(deal.source, "europroduct")
        self.assertEqual(deal.source_label, "Europroduct")
        self.assertEqual(deal.title, "ჭურჭლის ჟელე 'ფეირი' ვაშლი 1ლ")
        self.assertEqual(deal.new_price, "8,59 ₾")
        self.assertEqual(deal.old_price, "11,55 ₾")
        self.assertEqual(
            deal.image,
            "https://images.europroduct.ge/prod/00d73fe13a/8001841618869.jpg?w=500",
        )

    def test_merge_locales_prefers_english_title_and_falls_back_to_georgian(self) -> None:
        english = [
            deals[0]
            for deals in [
                EuroproductApi.parse_promo_page(
                    """
                    <div class="product-grid-item js-product-item">
                        <div class="img-wrap">
                            <a class="js-add-to-cart" data-id="00D73FE13A"></a>
                        </div>
                        <div class="info-wrap">
                            <h2 class="product-name">Dish jelly / fairy / apple 1 l</h2>
                            <span class="product-price"><span class="new">8.59 ₾</span></span>
                        </div>
                    </div>
                    """,
                    "https://europroduct.ge/",
                )[0]
            ]
        ]
        georgian = [
            deals[0]
            for deals in [
                EuroproductApi.parse_promo_page(
                    """
                    <div class="product-grid-item js-product-item">
                        <div class="img-wrap">
                            <a class="js-add-to-cart" data-id="00D73FE13A"></a>
                        </div>
                        <div class="info-wrap">
                            <h2 class="product-name">ჭურჭლის ჟელე 'ფეირი' ვაშლი 1ლ</h2>
                            <span class="product-price"><span class="new">8,59 ₾</span></span>
                        </div>
                    </div>
                    """,
                    "https://europroduct.ge/",
                )[0]
            ]
        ]

        merged = EuroproductApi._merge_locales(english, georgian)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].title, "Dish jelly / fairy / apple 1 l")


if __name__ == "__main__":
    unittest.main()
