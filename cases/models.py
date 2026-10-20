from django.db import models

PREFIXES = {
    "pending": "BA",
    "correspondence": "OC",
    "documents": "CD",
    "tribunal": "TM",
}


class Case(models.Model):
    DEPARTMENTS = [
        ("pending", "Bureau of Pending Affairs"),
        ("correspondence", "Office of Correspondence Avoidance"),
        ("documents", "Commission for Unnecessarily Complicated Documents"),
        ("tribunal", "Tribunal for Minor Inconveniences"),
    ]
    STATUSES = [
        ("filed", "Filed"),
        ("under_review", "Under review"),
        ("resolved", "Resolved"),
        ("failed", "Failed"),
    ]

    number = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    department = models.CharField(max_length=20, choices=DEPARTMENTS)
    statement = models.TextField()
    status = models.CharField(max_length=20, choices=STATUSES, default="filed")
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"{PREFIXES[self.department]}-{2047 + self.pk}"
            super().save(update_fields=["number"])
