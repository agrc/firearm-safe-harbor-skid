"""
config.py: Configuration values. Secrets to be handled with Secrets Manager
"""

import logging

SKID_NAME = "firearm-safe-harbor-skid"

AGOL_ORG = "https://utah.maps.arcgis.com"
SENDGRID_SETTINGS = {
    "from_address": "noreply@utah.gov",
    "to_addresses": "ugrc-developers@utah.gov",
    "prefix": SKID_NAME,
}
LOG_LEVEL = logging.DEBUG
LOG_FILE_NAME = "log"
PARTICIPATION_COLUMN = "Firearm Safe Harbor (FSH) Participating"
COLUMNS = [
    "Firearm Safe Harbor (FSH) Participating",
    "NAME",
    "PHONE",
    "WEBSITE",
    "EMAIL",
    "FSH AVAILABILITY",
    "FSH NOTES",
    "ADDRESS",
    "ADDRESS2",
    "GOOGLE",
    "X",
    "Y",
]
