"""Per-user permissions (tester feedback: "what can a cashier do vs a manager?").

* role "admin"  → every permission, plus settings / users / privacy (admin-only).
* any other role → exactly the permissions ticked on the user (users.permissions),
  usually started from a template (cashier / supervisor / storekeeper).

The server enforces these on every endpoint (require_perm); the screens only
hide what the user can't use.
"""
from fastapi import Depends, HTTPException, status

# key: (Arabic label, group, Arabic description)
CATALOG = {
    "sell":           ("البيع وإصدار الفواتير", "البيع", "نقطة البيع، الفواتير، المسودات، إضافة عميل"),
    "donate":         ("استلام التبرعات", "البيع", "إصدار إيصالات التبرع"),
    "returns":        ("المرتجعات والإشعارات الدائنة", "البيع", "إرجاع منتجات من فاتورة وإصدار إشعار دائن"),
    "void_donations": ("إلغاء إيصالات التبرع", "البيع", "إلغاء إيصال تبرع مع ذكر السبب"),
    "register_close": ("إغلاق الصندوق", "البيع", "تقرير Z وجرد النقد آخر اليوم"),
    "products":       ("المنتجات والأسعار", "المخزون", "إضافة وتعديل المنتجات والأسعار والتصنيفات ووحدات القياس"),
    "stock_adjust":   ("تعديل الكميات", "المخزون", "إدخال مخزون وتسوية الكميات"),
    "receiving":      ("استلام البضاعة", "المخزون", "سندات استلام البضاعة من الموردين"),
    "purchasing":     ("أوامر الشراء", "المخزون", "إنشاء أوامر الشراء وتعديلها وإرسالها"),
    "po_approve":     ("اعتماد أوامر الشراء", "المخزون", "اعتماد أمر الشراء قبل استلامه"),
    "suppliers":      ("الموردون", "المخزون", "إضافة الموردين ومستنداتهم واعتمادها"),
    "consignment":    ("الأمانات", "المخزون", "استلام الأمانات وتسويتها وإرجاعها"),
    "reports":        ("التقارير ولوحة التحكم", "الإدارة", "تقارير المبيعات والتبرعات والأرقام المالية"),
    "customers":      ("تعديل وحذف العملاء", "الإدارة", "تعديل بيانات العملاء وحذفهم"),
    "branches":       ("الفروع والصناديق", "الإدارة", "إضافة الفروع والصناديق وتعديلها"),
}
ALL = list(CATALOG)

TEMPLATES = {
    "cashier":     ("كاشير / متطوع", ["sell", "donate", "register_close"]),
    "supervisor":  ("مشرف", ["sell", "donate", "returns", "void_donations", "register_close",
                             "reports", "customers", "stock_adjust", "receiving"]),
    "storekeeper": ("أمين مخزن", ["products", "stock_adjust", "receiving", "purchasing", "suppliers"]),
}
ROLE_LABELS = {"admin": "مدير النظام", "custom": "صلاحيات مخصصة",
               **{k: v[0] for k, v in TEMPLATES.items()}}
ROLES = set(ROLE_LABELS)


def clean(perms) -> list[str]:
    return sorted({p for p in (perms or []) if p in CATALOG}, key=ALL.index)


def effective(user) -> list[str]:
    if getattr(user, "role", None) == "admin":
        return list(ALL)
    perms = getattr(user, "permissions", None)
    if perms is None:                                   # user not migrated yet: role template
        perms = TEMPLATES.get(getattr(user, "role", ""), ("", TEMPLATES["cashier"][1]))[1]
    return clean(perms)


def has(user, key: str) -> bool:
    return key in effective(user)


def require_perm(*keys: str):
    """Allow when the user has ANY of `keys` (admins always)."""
    from routers.auth import get_current_user

    def dep(user=Depends(get_current_user)):
        if user.role == "admin" or any(has(user, k) for k in keys):
            return user
        label = "، ".join(CATALOG[k][0] for k in keys)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"ليست لديك صلاحية: {label}")
    dep.__name__ = "require_perm_" + "_".join(keys)
    return dep


def catalog_out() -> dict:
    return {
        "permissions": [{"key": k, "label": v[0], "group": v[1], "description": v[2]} for k, v in CATALOG.items()],
        "templates": [{"key": k, "label": v[0], "permissions": v[1]} for k, v in TEMPLATES.items()],
        "admin_only": ["الإعدادات وبيانات المنشأة", "المستخدمون والصلاحيات", "الخصوصية وحذف البيانات"],
    }
