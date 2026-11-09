from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    description: str
    instructions: str
    greeting: str
    required_fields: tuple[str, ...]
    goals: tuple[tuple[str, str], ...]
    completion: str


ROLES = MappingProxyType({
    "general": Role(
        "general", "General Information Collection Agent",
        "Collect a reason for contact and preferred follow-up time.",
        "Collect contact details only; do not give medical advice.",
        "I am Arogya Caller, an AI assistant. I collect your reason for contact and preferred follow-up time; your name is optional. Do you consent?",
        ("reason_for_contact", "preferred_follow_up_time"),
        (("user_name", "Optional name"), ("reason_for_contact", "Reason for contact"),
         ("preferred_follow_up_time", "Specific preferred follow-up time")),
        "Thank you. Your confirmed information has been saved."),
    "appointment": Role(
        "appointment", "Appointment Request Agent",
        "Collect an appointment request; this does not book an appointment.",
        "Collect an appointment request only. Never promise a booking or provide medical advice.",
        "I am Arogya Caller, an AI assistant. I collect your appointment purpose, preferred date and time to record a request, not a booking. Do you consent?",
        ("appointment_purpose", "preferred_date", "preferred_time"),
        (("appointment_purpose", "Appointment purpose"), ("preferred_date", "Future date YYYY-MM-DD"),
         ("preferred_time", "Time HH:MM in 24-hour format")),
        "Thank you. Your confirmed appointment request has been saved; it is not a booking.")
})
