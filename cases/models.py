from django.db import models

PREFIXES = {
    "pending": "BA",
    "correspondence": "OC",
    "documents": "CD",
    "tribunal": "TM",
    "briefing": "MD",
}


class Case(models.Model):
    DEPARTMENTS = [
        ("pending", "Bureau of Pending Affairs"),
        ("correspondence", "Office of Correspondence Avoidance"),
        ("documents", "Commission for Unnecessarily Complicated Documents"),
        ("tribunal", "Tribunal for Minor Inconveniences"),
        ("briefing", "Morning Docket Office"),
    ]
    STATUSES = [
        ("filed", "Filed"),
        ("under_review", "Under review"),
        ("resolved", "Resolved"),
        ("failed", "Failed"),
    ]

    # Legal status changes. Resolved is final; a failed case may be re-reviewed.
    TRANSITIONS = {
        "filed": {"under_review"},
        "under_review": {"resolved", "failed"},
        "failed": {"under_review"},
        "resolved": set(),
    }

    number = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    department = models.CharField(max_length=20, choices=DEPARTMENTS)
    statement = models.TextField()
    status = models.CharField(max_length=20, choices=STATUSES, default="filed")
    result = models.JSONField(null=True, blank=True)
    options = models.JSONField(default=dict, blank=True)  # e.g. {"tone": "firm"}
    done_tasks = models.JSONField(default=list, blank=True)  # indexes of Pending tasks the user ticked off
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"{PREFIXES[self.department]}-{2047 + self.pk}"
            super().save(update_fields=["number"])

    def transition(self, new_status):
        """Move to new_status (saving the case), or raise ValueError if the move is not allowed."""
        if new_status not in self.TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Illegal status change: {self.status} -> {new_status}")
        self.status = new_status
        self.save()
