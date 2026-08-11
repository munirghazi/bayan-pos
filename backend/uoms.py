"""Unit-of-measure conversion. Conversions are valid only within a category.

result = qty * from_uom.factor / to_uom.factor, rounded to the target
category's decimal_places (or an explicit override).
"""


class UomConversionError(ValueError):
    pass


def convert(qty, from_uom, to_uom, round_dp: int | None = None) -> float:
    if from_uom is None or to_uom is None:
        raise UomConversionError("وحدة غير محددة")
    if from_uom.category_id != to_uom.category_id:
        raise UomConversionError("لا يمكن التحويل بين وحدتين من فئتين مختلفتين")
    ffrom = float(from_uom.factor or 0)
    fto = float(to_uom.factor or 0)
    if fto == 0:
        raise UomConversionError("معامل تحويل غير صالح")
    result = float(qty) * ffrom / fto
    if round_dp is None:
        cat = getattr(to_uom, "category", None)
        round_dp = cat.decimal_places if cat is not None else 3
    return round(result, int(round_dp))
