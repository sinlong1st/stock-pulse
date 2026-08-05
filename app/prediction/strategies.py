"""Prediction strategies — the natural-language framework the AI reasons with.

A strategy shapes *how* the AI weighs the (real) signals + news into a lean — it
never changes the numbers, the output format, or the disclaimers (those are fixed
guardrails in the analyst). The built-in default is visible to users for
transparency; custom per-user strategies come in the Pro/multi-user era.
See specs/STOCKPULSE_AI_PREDICTION_PLAN.md §5.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Strategy:
    """A framework, plus the translations used to *show* it to the user.

    `body` is always the English text sent to the model — prompt instructions
    work best in one consistent language, and the analyst separately tells the
    model which language to write its answer in. `name_vi`/`body_vi` exist only
    for display. A future user-written strategy has no translation, so display
    falls back to what they typed.
    """

    id: str
    name: str
    body: str  # the natural-language framework — ALWAYS the prompt text
    builtin: bool = True
    name_vi: str | None = None
    body_vi: str | None = None

    def display(self, vi: bool) -> tuple[str, str]:
        """(name, body) as the user should read them."""
        if vi:
            return (self.name_vi or self.name, self.body_vi or self.body)
        return (self.name, self.body)


DEFAULT_STRATEGY = Strategy(
    id="default",
    name="StockPulse Balanced",
    body=(
        "Weigh three things for each horizon: (1) the materiality and direction of "
        "recent news, (2) the price trend, and (3) where the price sits in its range. "
        "A large discount can set up a bounce, but a falling trend can keep falling — "
        "don't call a bottom on cheapness alone. Short horizons (about a week) are "
        "driven mostly by fresh news and momentum; longer horizons (a month, three "
        "months) lean more on the trend and where value sits. When the signals "
        "conflict or the news is thin, prefer 'hold' with low confidence. Be honest "
        "and never imply certainty."
    ),
    builtin=True,
    name_vi="StockPulse Cân bằng",
    body_vi=(
        "Cân nhắc ba yếu tố cho mỗi khung thời gian: (1) mức độ quan trọng và chiều "
        "hướng của tin tức gần đây, (2) xu hướng giá, và (3) vị trí của giá trong biên "
        "độ. Mức chiết khấu sâu có thể tạo đà hồi phục, nhưng xu hướng giảm vẫn có thể "
        "giảm tiếp — đừng kết luận đã tạo đáy chỉ vì giá rẻ. Khung ngắn (khoảng một "
        "tuần) chủ yếu do tin mới và đà giá quyết định; khung dài hơn (một tháng, ba "
        "tháng) dựa nhiều hơn vào xu hướng và vùng định giá. Khi các tín hiệu mâu "
        "thuẫn hoặc tin tức thưa thớt, hãy ưu tiên 'đi ngang' với độ tin cậy thấp. "
        "Hãy trung thực và không bao giờ ngụ ý chắc chắn."
    ),
)
