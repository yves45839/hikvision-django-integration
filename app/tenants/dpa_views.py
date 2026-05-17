"""
PHASE 6.7 — DPA (Data Processing Agreement) téléchargeable
"""
import datetime

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


class DPADownloadView(APIView):
    """
    Génère et retourne un DPA (Data Processing Agreement) simple.
    Art. 28 RGPD: accord de traitement des données.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        date = datetime.date.today().isoformat()

        content = f"""DATA PROCESSING AGREEMENT (DPA)
SecurePoint / Hikvision Integration Platform

================================================================================
DATE: {date}
CLIENT: {user.email}
PROCESSOR: Label CI SAS
================================================================================

1. OBJECT OF THIS AGREEMENT

This Data Processing Agreement ("DPA") is entered into between the Client
(hereinafter "Data Controller") and Label CI SAS (hereinafter "Data Processor").

The DPA governs the processing of personal data in connection with the SecurePoint
platform, which manages access control systems for Hikvision devices.

2. SCOPE OF PROCESSING

The Data Processor shall process personal data on behalf of the Data Controller as
follows:

2.1 Types of Personal Data Processed:
    - User identification data (name, email, username)
    - Biometric data (fingerprints, facial recognition - encrypted)
    - Access logs and attendance records
    - IP addresses and user agents
    - Device location and access point information

2.2 Categories of Data Subjects:
    - End-users and employees of the Data Controller
    - Visitors with access to controlled areas

2.3 Duration of Processing:
    - During the term of the Service Agreement
    - 90 days retention for access logs (configurable)
    - Immediate deletion of unprocessed biometric data
    - 1 year after account deletion (audit trail only)

2.4 Nature and Purpose of Processing:
    - Access control and authentication
    - Attendance tracking and time-keeping
    - Audit logging and security monitoring
    - Compliance with applicable regulations

3. DATA PROTECTION OBLIGATIONS

3.1 The Data Processor shall:
    - Process personal data only on documented instructions from the Data Controller
    - Ensure that persons authorized to process personal data are subject to
      confidentiality obligations
    - Implement appropriate technical and organizational security measures
    - Assist the Data Controller in responding to data subject rights requests
    - Delete or return all personal data after the end of processing
    - Provide proof of deletion upon request

3.2 The Data Processor shall NOT:
    - Process personal data outside the scope authorized by this DPA
    - Share personal data with unauthorized recipients
    - Sell or commercialize personal data
    - Transfer data to countries without adequate data protection

4. SUB-PROCESSORS

The Data Processor may engage sub-processors only with prior written approval from
the Data Controller. A current list of approved sub-processors is available at:
https://label-ci.com/legal/sub-processors/

5. INTERNATIONAL DATA TRANSFERS

To the extent personal data is transferred outside the European Economic Area,
such transfers shall be governed by Standard Contractual Clauses (SCCs) as approved
by the European Commission.

6. DATA SUBJECT RIGHTS

The Data Processor shall:
    - Assist the Data Controller in fulfilling data subject requests for:
      * Access to data (Article 15 GDPR)
      * Rectification of inaccurate data (Article 16 GDPR)
      * Erasure/Right to be Forgotten (Article 17 GDPR)
      * Restriction of processing (Article 18 GDPR)
      * Data portability (Article 20 GDPR)
      * Objection to processing (Article 21 GDPR)

7. SECURITY MEASURES

The Data Processor implements the following technical measures:
    - Encryption of sensitive data (AES-256, Fernet)
    - Multi-factor authentication for administrative access
    - Regular security audits and penetration testing
    - Database access controls and field-level encryption
    - Audit logging of all data access
    - Incident response procedures

8. AUDIT AND COMPLIANCE

The Data Processor shall:
    - Maintain detailed records of processing activities
    - Provide audit reports upon request (max 2x per year)
    - Allow data protection impact assessments (DPIAs)
    - Report security incidents within 24 hours of discovery
    - Comply with data protection authority requests

9. DATA RETENTION AND DELETION

Unless otherwise instructed by the Data Controller:
    - Access logs: deleted after 90 days (configurable)
    - User profiles: deleted 1 year after account closure
    - Biometric templates: never stored unless explicit consent
    - Backup data: deleted according to backup retention policy (30 days default)

10. TERM AND TERMINATION

This DPA shall remain in effect for the duration of the Service Agreement.
Upon termination or expiration:
    - The Data Processor shall delete all personal data within 30 days
    - A certificate of deletion shall be provided
    - The Data Controller may request return of data instead of deletion

11. LIABILITY AND INDEMNIFICATION

The Data Processor agrees to indemnify the Data Controller for:
    - Unauthorized data access or breaches caused by the Data Processor
    - Violation of applicable data protection laws
    - Failures to implement required security measures
    - Unauthorized sub-processor engagement

12. CONTACT INFORMATION

For data protection inquiries:
    Email: privacy@label-ci.com
    Phone: +33 (0) XX XX XX XX
    Address: Label CI SAS, [Address], France

For GDPR-related requests:
    Email: dpo@label-ci.com
    (Data Protection Officer)

================================================================================

IN WITNESS WHEREOF, the parties have executed this DPA as of the date first written above.

DATA CONTROLLER (Client)
Name: {user.email}
Signature: ___________________________
Date: {date}

DATA PROCESSOR (Label CI SAS)
Authorized Signatory: ___________________________
Date: {date}

================================================================================

This DPA is effective as of {date} and supersedes all previous data processing
agreements between the parties. This document is subject to modification according
to changes in applicable law and the Service Agreement terms.
"""

        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="DPA_SecurePoint_{user.id}_{date}.txt"'
        )
        return response
