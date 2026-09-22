"""Choice enumerations for the consultancy app.

Choices live in their own module rather than inlined as tuples on each model
field, per the project-wide convention (see ``customers/choices.py``).

The two case types share three of these enums on purpose - ``VisaDecisionChoices``,
``BiometricsStatusChoices`` and (via the base) the currency - because the
underlying real-world process is the same. Everything else is specific to one
case type: a study-visa case has an institution pipeline, an English test and
financial evidence, and none of that belongs on a family-visit visa case.

Where a status chain is long, the docstring says what separates the adjacent
states, because that is the part staff get wrong.
"""

from django.db import models


class VisaCategoryChoices(models.TextChoices):
    """Which kind of general visa this case is for.

    Drives the document checklist, the fee and which embassy/VAC handles it, so it
    is a controlled field rather than a label on the case title. ``WORK`` is here
    rather than in a separate app because the *consultancy workflow* is identical -
    the difference is which forms get filled in.
    """

    VISIT_TOURIST = 'VISIT_TOURIST', 'Visit / Tourist'
    BUSINESS = 'BUSINESS', 'Business'
    FAMILY = 'FAMILY', 'Family'
    TRANSIT = 'TRANSIT', 'Transit'
    WORK = 'WORK', 'Work'
    OTHER = 'OTHER', 'Other'


class VisaCaseStatusChoices(models.TextChoices):
    """The general visa case pipeline, from first consultation to closed file.

    The chain is long because a visa case genuinely has this many distinguishable
    states, and collapsing them loses the only thing the status is for - knowing
    what happens next.

    * CONSULTATION - the client has been advised, no commitment yet.
    * DOCUMENTS_PENDING - we are waiting on the client, not on anyone else. This
      is the state cases sit in for weeks, and the one worth chasing.
    * READY_TO_APPLY - documents are in; the application has not gone out yet.
    * SUBMITTED - lodged with the embassy/VAC. ``IN_PROCESS`` is deliberately
      separate: submitted means "we sent it", in-process means "they have opened
      it", and the gap between the two is where appointment scheduling lives.
    * APPROVED / REFUSED - the decision. Both are terminal *decisions*, not
      terminal *cases*.
    * CLOSED - the file is finished and the passport returned. A case can be
      CLOSED after APPROVED or after REFUSED, which is why CLOSED is its own
      state rather than being folded into either outcome. Reports count decisions
      from APPROVED/REFUSED and workload from everything else.
    """

    CONSULTATION = 'CONSULTATION', 'Consultation'
    DOCUMENTS_PENDING = 'DOCUMENTS_PENDING', 'Documents Pending'
    READY_TO_APPLY = 'READY_TO_APPLY', 'Ready to Apply'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    IN_PROCESS = 'IN_PROCESS', 'In Process'
    APPROVED = 'APPROVED', 'Approved'
    REFUSED = 'REFUSED', 'Refused'
    CLOSED = 'CLOSED', 'Closed'


class BiometricsStatusChoices(models.TextChoices):
    """Biometrics enrolment state, shared by both case types.

    NOT_REQUIRED is the default-ish blank answer because a great many
    nationalities and destinations do not require biometrics at all, and that is
    different information from "required but not yet done".
    """

    NOT_REQUIRED = 'NOT_REQUIRED', 'Not Required'
    PENDING = 'PENDING', 'Pending'
    BOOKED = 'BOOKED', 'Appointment Booked'
    COMPLETED = 'COMPLETED', 'Completed'


class DocumentChecklistStatusChoices(models.TextChoices):
    """How complete the client's document pack is.

    Readiness is the single biggest predictor of whether a case moves, so it is a
    status field rather than an attachment count. SUBMITTED is separate from
    COMPLETE because a pack can be complete and still not handed over.
    """

    NOT_STARTED = 'NOT_STARTED', 'Not Started'
    INCOMPLETE = 'INCOMPLETE', 'Incomplete'
    COMPLETE = 'COMPLETE', 'Complete'
    SUBMITTED = 'SUBMITTED', 'Submitted'


class VisaDecisionChoices(models.TextChoices):
    """The outcome of a visa application, shared by both case types.

    Reused rather than duplicated because the two sheets' outcomes overlap almost
    entirely, and two near-identical enums would drift the first time one of them
    gained a value.

    WITHDRAWN means the *client* pulled the application; DEFERRED means the
    decision was postponed rather than made. Neither is a refusal, and reporting
    them as one would misstate the refusal rate - which is exactly the number this
    kind of business watches.
    """

    APPROVED = 'APPROVED', 'Approved'
    REFUSED = 'REFUSED', 'Refused'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'
    DEFERRED = 'DEFERRED', 'Deferred'
    OTHER = 'OTHER', 'Other'


class PassportCollectionStatusChoices(models.TextChoices):
    """Where the client's passport is between decision and hand-back.

    The passport is the client's most valuable document and the thing they call
    about. COURIERED is distinct from COLLECTED because responsibility differs:
    once it is with a courier, the counter cannot answer "is it ready".
    """

    PENDING = 'PENDING', 'Pending'
    READY = 'READY', 'Ready for Collection'
    COLLECTED = 'COLLECTED', 'Collected'
    COURIERED = 'COURIERED', 'Couriered'


class StudyLevelChoices(models.TextChoices):
    """Academic level of the course being applied for.

    SCHOOL_COLLEGE covers under-18 and pathway applications, which run a different
    process (guardianship, different financial rules) - hence its own value rather
    than being squeezed into FOUNDATION.
    """

    DIPLOMA = 'DIPLOMA', 'Diploma'
    FOUNDATION = 'FOUNDATION', 'Foundation'
    BACHELORS = 'BACHELORS', "Bachelor's"
    MASTERS = 'MASTERS', "Master's"
    PHD = 'PHD', 'PhD'
    SCHOOL_COLLEGE = 'SCHOOL_COLLEGE', 'School / College'
    OTHER = 'OTHER', 'Other'


class InstitutionApplicationStatusChoices(models.TextChoices):
    """The institution-admission pipeline, ahead of the visa application itself.

    A study-visa case spends most of its life here, not in the visa stage, which
    is why admissions is a full pipeline rather than a boolean. The offer states
    are separate from ACCEPTED because an offer is the institution's move and
    acceptance is the client's.
    """

    NOT_APPLIED = 'NOT_APPLIED', 'Not Applied'
    APPLIED = 'APPLIED', 'Applied'
    CONDITIONAL_OFFER = 'CONDITIONAL_OFFER', 'Conditional Offer'
    UNCONDITIONAL_OFFER = 'UNCONDITIONAL_OFFER', 'Unconditional Offer'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    DEFERRED = 'DEFERRED', 'Deferred'


class OfferAcceptanceStatusChoices(models.TextChoices):
    """Whether the client has taken up an offer, and on what basis.

    Separate from ``InstitutionApplicationStatusChoices.ACCEPTED`` because the two
    answer different questions: what the institution offered, versus what the
    client did about it. NOT_APPLICABLE exists so a case with no offer yet is not
    forced to look pending.
    """

    PENDING = 'PENDING', 'Pending'
    CONDITIONAL = 'CONDITIONAL', 'Conditional'
    UNCONDITIONAL = 'UNCONDITIONAL', 'Unconditional'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'


class EnglishTestTypeChoices(models.TextChoices):
    """Which English proficiency test the client sat.

    The type matters as much as the result, because each institution accepts a
    different subset and the scores are not comparable across tests - which is why
    ``english_test_score`` is stored as text rather than a number.
    """

    IELTS = 'IELTS', 'IELTS'
    PTE = 'PTE', 'PTE'
    TOEFL = 'TOEFL', 'TOEFL'
    OTHER = 'OTHER', 'Other'


class AcademicDocumentsStatusChoices(models.TextChoices):
    """Readiness of the academic document pack (transcripts, certificates).

    VERIFIED is distinct from COMPLETE because a complete pack can still contain
    documents nobody has checked against the originals, and institutions reject on
    exactly that.
    """

    INCOMPLETE = 'INCOMPLETE', 'Incomplete'
    COMPLETE = 'COMPLETE', 'Complete'
    VERIFIED = 'VERIFIED', 'Verified'
    SUBMITTED = 'SUBMITTED', 'Submitted'


class SOPStatusChoices(models.TextChoices):
    """Statement-of-purpose drafting state.

    The SOP is often the longest-lead item on a study case and the one clients
    return late, so it is tracked separately from the rest of the document pack
    rather than being an attachment nobody can see the status of.
    """

    NOT_STARTED = 'NOT_STARTED', 'Not Started'
    DRAFT = 'DRAFT', 'Draft'
    FINAL = 'FINAL', 'Final'
    SUBMITTED = 'SUBMITTED', 'Submitted'


class FinancialEvidenceStatusChoices(models.TextChoices):
    """Readiness of proof-of-funds evidence.

    NOT_REQUIRED is a real answer for destinations and cases where funds are not
    assessed; without it staff would have to leave the field blank and lose the
    distinction between "not needed" and "not started".
    """

    NOT_STARTED = 'NOT_STARTED', 'Not Started'
    INCOMPLETE = 'INCOMPLETE', 'Incomplete'
    COMPLETE = 'COMPLETE', 'Complete'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    NOT_REQUIRED = 'NOT_REQUIRED', 'Not Required'


class EnrolmentReferenceTypeChoices(models.TextChoices):
    """Which country-specific enrolment reference the institution issued.

    Country is a free-text field on the case, so the reference *type* is what
    tells a reader which country's system this case actually sits in (CAS = UK,
    CoE = Australia, I-20 = USA, LOA = Canada). One field instead of four nullable
    country columns, per the spec's country-flexible requirement.
    """

    CAS = 'CAS', 'CAS (UK)'
    COE = 'COE', 'CoE (Australia)'
    I20 = 'I20', 'I-20 (USA)'
    LOA = 'LOA', 'LOA (Canada)'
    OTHER = 'OTHER', 'Other'


class StudyVisaApplicationStatusChoices(models.TextChoices):
    """The study-visa application pipeline, after admissions is settled.

    Deliberately parallel to ``VisaCaseStatusChoices`` but not the same enum: the
    study chain cannot start until an enrolment reference exists
    (NOT_READY), and it has BIOMETRICS as a first-class stage because it is
    mandatory for the main study destinations.
    """

    NOT_READY = 'NOT_READY', 'Not Ready'
    READY_TO_APPLY = 'READY_TO_APPLY', 'Ready to Apply'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    BIOMETRICS = 'BIOMETRICS', 'Biometrics'
    IN_PROCESS = 'IN_PROCESS', 'In Process'
    APPROVED = 'APPROVED', 'Approved'
    REFUSED = 'REFUSED', 'Refused'
    CLOSED = 'CLOSED', 'Closed'


class MedicalTBStatusChoices(models.TextChoices):
    """Tuberculosis screening state, required by several study destinations.

    NOT_REQUIRED again carries real information - most destinations do not ask for
    it, and blank would hide that.
    """

    NOT_REQUIRED = 'NOT_REQUIRED', 'Not Required'
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
